import logging
import os
import sys
from io import StringIO

# Suppress transformers library output
logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

# Suppress stderr during imports
old_stderr = sys.stderr
sys.stderr = StringIO()

try:
    from langchain_chroma import Chroma
    from langchain_classic.chains import (
        create_history_aware_retriever,
        create_retrieval_chain,
    )
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_community.chat_message_histories import ChatMessageHistory
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables.history import RunnableWithMessageHistory
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from tenacity import retry, stop_after_attempt, wait_exponential
finally:
    sys.stderr = old_stderr

from legal_ai.core import constants, settings, tracing
from legal_ai.services import vector_store


class LegalChat:
    """Conversational RAG agent (history-aware retriever + session store)."""

    def __init__(self, session_id: str):
        # Instance-level store: a class-level dict would be shared by every
        # LegalChat instance in the process, leaking chat history between
        # sessions and never being freed by clear_chat_cache().
        self.store: dict[str, ChatMessageHistory] = {}
        app_settings = settings.get_settings()
        gemini_key = settings.get_gemini_api_key()

        embeddings = HuggingFaceEmbeddings(
            model_name=constants.EMBEDDING_MODEL_NAME,
        )
        self.session_id = session_id

        llm = ChatGoogleGenerativeAI(
            model=app_settings.llm_model,
            api_key=gemini_key,
        )

        client = vector_store.get_chroma_client()

        db = Chroma(
            client=client,
            collection_name=constants.COLLECTION_NAME,
            embedding_function=embeddings,
        )
        retriever = db.as_retriever(search_kwargs={"k": app_settings.retrieval_top_k})

        contextualize_q_system_prompt = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, formulate a standalone question "
            "which can be understood without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is."
        )

        contextualize_q_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", contextualize_q_system_prompt),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )

        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, contextualize_q_prompt
        )

        qa_system_prompt = (
            "You are an assistant for question-answering tasks about EU legal documents, "
            "especially the EU Artificial Intelligence Act. "
            "Use the following pieces of retrieved context to answer the question. "
            "If you don't know the answer, just say that you don't know. "
            "Use three sentences maximum and keep the answer concise.\n\n"
            "{context}"
        )

        qa_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", qa_system_prompt),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )

        question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

        self.rag_chain = RunnableWithMessageHistory(
            rag_chain,
            self.get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        if session_id not in self.store:
            self.store[session_id] = ChatMessageHistory()
        return self.store[session_id]

    def load_history_from_db(self, messages: list[dict]) -> None:
        """Populate LangChain chat history from persisted audit_log rows."""
        history = self.get_session_history(self.session_id)
        history.clear()
        for row in messages:
            role = row["role"]
            content = row["content"]
            if role == "user":
                history.add_user_message(content)
            elif role == "assistant":
                history.add_ai_message(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def ask(self, question: str, user_id: str = None) -> str:
        """Process a question through the RAG chain with tracing support.

        Best practice: Include user_id for audit trails and cost attribution.
        LangFuse automatically captures tokens, latency, and chain hierarchy.

        Args:
            question: User's question
            user_id: User identifier for tracing context

        Returns:
            Assistant's answer (RAG-enhanced with retrieved context)
        """
        callbacks = tracing.get_langfuse_callback(
            trace_name="legal-rag-query",
            user_id=user_id,
            session_id=self.session_id,
            tags=["question-answering", "eu-ai-act", "retrieval-augmented"],
        )

        response = self.rag_chain.invoke(
            {"input": question},
            config={
                "configurable": {"session_id": self.session_id},
                "callbacks": callbacks,
                # langfuse >= 3 reads trace context from metadata; older
                # versions ignore these keys (handler kwargs are used instead).
                "metadata": {
                    "langfuse_session_id": self.session_id,
                    "langfuse_user_id": user_id,
                    "langfuse_tags": ["question-answering", "eu-ai-act", "retrieval-augmented"],
                },
            },
        )["answer"]
        return response

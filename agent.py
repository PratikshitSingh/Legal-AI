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
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

import utils as Utils


class LegalChat:
    """Conversational RAG agent (history-aware retriever + session store)."""

    store: dict[str, ChatMessageHistory] = {}
    session_id: str = ""
    rag_chain = None

    def __init__(self, session_id: str):
        config = Utils.load_config()
        llm_cfg = config["llm"]
        emb_cfg = Utils.get_embedding_settings()
        gemini_key = Utils.get_gemini_api_key()

        embeddings = GoogleGenerativeAIEmbeddings(
            model=emb_cfg["model"],
            google_api_key=gemini_key,
        )
        self.session_id = session_id

        llm = ChatGoogleGenerativeAI(
            model=llm_cfg["model"],
            api_key=gemini_key,
        )

        client = Utils.get_chroma_client()

        db = Chroma(
            client=client,
            collection_name=Utils.COLLECTION_NAME,
            embedding_function=embeddings,
        )
        retriever = db.as_retriever()

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
        rag_chain = create_retrieval_chain(
            history_aware_retriever, question_answer_chain
        )

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
    def ask(self, question: str) -> str:
        response = self.rag_chain.invoke(
            {"input": question},
            config={"configurable": {"session_id": self.session_id}},
        )["answer"]
        return response


# Alias matching upstream firica/legalai naming
NewsChat = LegalChat

"""Services layer: chat routing, document management, ingestion, vector store, email.

Modules are imported explicitly (``from legal_ai.services import chat_service``)
rather than re-exported here — several pull in heavy ML dependencies, and the
package must stay cheap to import.
"""

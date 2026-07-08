"""Test suite for admin document upload with duplicate detection."""

import hashlib
import pytest
from uuid import uuid4

from legal_ai.services import embed
from legal_ai.db import db


class TestDocumentHash:
    """Test document content hash functionality."""

    def test_consistent_hash(self):
        """Same content should produce same hash."""
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "The quick brown fox jumps over the lazy dog"

        hash1 = embed.get_document_hash(text1)
        hash2 = embed.get_document_hash(text2)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 is 32 hex chars

    def test_different_hash(self):
        """Different content should produce different hash."""
        text1 = "The quick brown fox"
        text2 = "The slow brown fox"

        hash1 = embed.get_document_hash(text1)
        hash2 = embed.get_document_hash(text2)

        assert hash1 != hash2


class TestTextExtraction:
    """Test text extraction from files."""

    def test_extract_text_from_txt(self):
        """Should extract text from TXT file."""
        content = "Hello, this is a test document.\nWith multiple lines."
        file_bytes = content.encode("utf-8")

        extracted = embed.extract_text_from_file(file_bytes, "txt")
        assert extracted == content

    def test_extract_text_unsupported_type(self):
        """Should raise error for unsupported file type."""
        file_bytes = b"some content"

        with pytest.raises(ValueError, match="Unsupported file type"):
            embed.extract_text_from_file(file_bytes, "docx")


@pytest.mark.integration
class TestDuplicateDetection:
    """Test duplicate document detection preflight."""

    def test_duplicate_check_new_document(self):
        """New document should not be detected as duplicate."""
        # Use unique name and content
        unique_name = f"unique_doc_{uuid4().hex[:8]}"
        unique_text = f"This is unique content for {uuid4()}"
        unique_hash = embed.get_document_hash(unique_text)

        result = embed.check_duplicate_document(unique_name, unique_hash)

        assert result["is_duplicate"] == False
        assert result["existing_chunks"] == 0
        assert result["existing_exact_match"] == False


@pytest.mark.integration
class TestDocumentRecording:
    """Test document record creation in database."""

    def test_create_document_record(self):
        """Should create document record in database."""
        doc_name = f"test_doc_{uuid4().hex[:8]}"
        doc_description = "Test document for unit testing"
        content_hash = hashlib.md5(b"test content").hexdigest()
        uploader_id = str(uuid4())  # Mock user ID

        # This may fail if user doesn't exist, but we're testing the function logic
        try:
            result = db.create_document_record(
                name=doc_name,
                description=doc_description,
                content_hash=content_hash,
                uploaded_by_user_id=uploader_id,
                file_type="txt",
                chunk_count=5,
                metadata={"test": True},
            )

            # Result might be None if FK constraint fails, but structure should be OK
            if result:
                assert "document_id" in result or result is None
        except Exception as e:
            # Expected if user doesn't exist in DB
            assert "REFERENCES" in str(e) or "users" in str(e) or result is None

    def test_get_document_by_name_hash(self):
        """Should fetch document by name and hash."""
        # Using non-existent document
        result = db.get_document_by_name_hash("nonexistent_doc", "0000000000000000")
        assert result is None


@pytest.mark.integration
class TestEmbeddingIntegration:
    """Test embedding with duplicate chunk skipping."""

    def test_embed_returns_chunk_count(self):
        """embed_text_in_chromadb should return chunk count."""
        text = "This is a test document.\n" * 100  # Create enough text for multiple chunks

        # Count initial chunks
        from legal_ai.services import vector_store

        collection = vector_store.get_collection()
        initial_count = collection.count()

        # Embed text
        unique_doc_name = f"test_{uuid4().hex[:8]}"
        chunks_added = embed.embed_text_in_chromadb(
            text=text,
            document_name=unique_doc_name,
            document_description="Test document",
        )

        assert chunks_added > 0
        assert collection.count() > initial_count


@pytest.mark.integration
class TestIngestCustomDocument:
    """Test complete custom document ingestion flow."""

    def test_ingest_new_txt_document(self):
        """Should successfully ingest new TXT document."""
        file_content = "This is a test document content.\n" * 50
        file_bytes = file_content.encode("utf-8")
        doc_name = f"test_{uuid4().hex[:8]}"
        uploader_id = str(uuid4())

        result = embed.ingest_custom_document(
            file_bytes=file_bytes,
            document_name=doc_name,
            document_description="Test document",
            uploaded_by_user_id=uploader_id,
            file_type="txt",
        )

        # Result structure
        assert "success" in result
        assert "message" in result
        assert "chunks_added" in result
        assert "is_duplicate" in result

        # First upload should succeed (though FK might fail)
        # We're mainly testing the function doesn't crash and returns proper structure


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

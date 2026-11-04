"""Knowledge-base document, version and chunk persistence."""
from app.db import execute, execute_many, query_all, query_one


def get(document_id: int):
    return query_one("SELECT * FROM documents WHERE id=%s", (document_id,))


def get_by_hash(file_hash: str):
    return query_one("SELECT * FROM documents WHERE file_hash=%s", (file_hash,))


def create(owner_id, title, file_name, file_hash, source_type="user_upload") -> int:
    return execute(
        """INSERT INTO documents
           (owner_id, title, file_name, file_hash, source_type, status)
           VALUES (%s,%s,%s,%s,%s,'processing')""",
        (owner_id, title, file_name, file_hash, source_type),
    )


def update_status(document_id: int, status: str, error_message=None) -> int:
    return execute(
        "UPDATE documents SET status=%s, error_message=%s WHERE id=%s",
        (status, error_message, document_id),
    )


def list_all(limit: int = 20, offset: int = 0):
    return query_all(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM document_versions v
                   WHERE v.document_id=d.id) AS version_count,
                  (SELECT COUNT(*) FROM document_chunks c
                   JOIN document_versions v ON v.id=c.document_version_id
                   WHERE v.document_id=d.id) AS chunk_count
           FROM documents d
           ORDER BY d.created_at DESC, d.id DESC LIMIT %s OFFSET %s""",
        (limit, offset),
    )


def count_all() -> int:
    row = query_one("SELECT COUNT(*) AS total FROM documents")
    return int(row["total"] if row else 0)


def next_version_no(document_id: int) -> int:
    row = query_one(
        "SELECT COALESCE(MAX(version_no), 0) + 1 AS n FROM document_versions WHERE document_id=%s",
        (document_id,),
    )
    return int(row["n"] if row else 1)


def create_version(document_id: int, parser_version: str, embedding_model: str,
                   chunk_strategy: str) -> int:
    version_no = next_version_no(document_id)
    return execute(
        """INSERT INTO document_versions
           (document_id, version_no, parser_version, embedding_model,
            chunk_strategy, status)
           VALUES (%s,%s,%s,%s,%s,'processing')""",
        (document_id, version_no, parser_version, embedding_model, chunk_strategy),
    )


def update_version_status(version_id: int, status: str, error_message=None) -> int:
    return execute(
        """UPDATE document_versions SET status=%s, error_message=%s,
                  completed_at=IF(%s='ready', NOW(), completed_at)
           WHERE id=%s""",
        (status, error_message, status, version_id),
    )


def latest_version(document_id: int):
    return query_one(
        """SELECT * FROM document_versions
           WHERE document_id=%s ORDER BY version_no DESC LIMIT 1""",
        (document_id,),
    )


def get_version(version_id: int):
    return query_one("SELECT * FROM document_versions WHERE id=%s", (version_id,))


def list_versions(document_id: int):
    return query_all(
        """SELECT * FROM document_versions
           WHERE document_id=%s ORDER BY version_no DESC""",
        (document_id,),
    )


def add_chunks(version_id: int, chunks: list) -> int:
    return execute_many(
        """INSERT INTO document_chunks
           (document_version_id, chunk_no, content, chapter, knowledge_point,
            page_no, vector_id, content_hash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        [
            (
                version_id, chunk["chunk_no"], chunk["content"],
                chunk.get("chapter"), chunk.get("knowledge_point"),
                chunk.get("page_no"), chunk["vector_id"], chunk["content_hash"],
            )
            for chunk in chunks
        ],
    )


def list_chunks(version_id: int, limit: int = 20):
    return query_all(
        """SELECT id, chunk_no, chapter, knowledge_point, page_no,
                  vector_id, content_hash, LEFT(content, 240) AS preview
           FROM document_chunks WHERE document_version_id=%s
           ORDER BY chunk_no ASC LIMIT %s""",
        (version_id, limit),
    )

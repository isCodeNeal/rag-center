import uuid

from app.utils.id_generator import (
    new_chunk_id,
    new_document_id,
    new_kb_id,
    new_retrieval_log_id,
)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def test_generated_ids_are_uuids_and_unique():
    for factory in (new_kb_id, new_document_id, new_chunk_id, new_retrieval_log_id):
        a, b = factory(), factory()
        assert _is_uuid(a) and _is_uuid(b)
        assert a != b

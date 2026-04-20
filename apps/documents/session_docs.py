"""Session-bound anonymous document IDs (beta try without login)."""
from __future__ import annotations

SESSION_ANON_IDS = "itr_anon_document_ids"


def register_anonymous_document(session, doc_id: int) -> None:
    ids = list(session.get(SESSION_ANON_IDS, []))
    if doc_id not in ids:
        ids.append(doc_id)
    session[SESSION_ANON_IDS] = ids
    session.modified = True


def owns_anonymous_document(session, doc_id: int) -> bool:
    return doc_id in session.get(SESSION_ANON_IDS, [])


def anonymous_document_count(session) -> int:
    return len(session.get(SESSION_ANON_IDS, []))

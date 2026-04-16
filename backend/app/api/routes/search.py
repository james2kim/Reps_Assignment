import json
import re

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.schemas.search import Citation, SearchRequest, SearchResponse
from backend.app.config import settings
from backend.app.core.answer_generator import generate_answer, generate_answer_stream
from backend.app.core.citations import build_citations
from backend.app.core.retrieval_router import route_query
from backend.app.core.scope_resolver import ScopeError, resolve_scope
from backend.app.db.session import get_db
from backend.app.models.enums import QueryIntent
from backend.app.repositories.chunk_repo import ChunkResult

router = APIRouter()


def _get_sync_client() -> anthropic.Anthropic | None:
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _get_async_client() -> anthropic.AsyncAnthropic | None:
    if not settings.anthropic_api_key:
        return None
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _filter_used_citations(
    citations: list[Citation],
    chunks: list[ChunkResult],
    answer_text: str,
) -> list[Citation]:
    """Only return citations the LLM actually referenced.

    Strategy: extract [Source N] from the answer, map to chunk asset_ids,
    then keep citations whose asset_id matches.
    """
    if not citations or not answer_text:
        return []

    # If the answer is a "not found" response, show no citations
    NOT_FOUND_SIGNALS = [
        "could not find",
        "couldn't find",
        "cannot find",
        "no information about that",
        "not found in your assigned",
    ]
    answer_lower = answer_text.lower()
    if any(signal in answer_lower for signal in NOT_FOUND_SIGNALS):
        return []

    # Strategy 1: extract [Source N] references
    referenced_nums = set(int(m) for m in re.findall(r"\[Source (\d+)", answer_text))

    referenced_asset_ids = set()
    for num in referenced_nums:
        idx = num - 1
        if 0 <= idx < len(chunks):
            chunk = chunks[idx]
            if chunk.asset_id:
                referenced_asset_ids.add(chunk.asset_id)

    # Strategy 2: scan answer for timestamps (e.g., "00:26") and file names
    # This catches cases where the LLM writes naturally instead of using [Source N]
    used = []
    for c in citations:
        keep = False
        # Matched via [Source N] -> asset_id
        if c.asset_id and c.asset_id in referenced_asset_ids:
            keep = True
        # Timestamp mentioned in answer text
        elif c.start and c.start in answer_text:
            keep = True
        # File name stem mentioned in answer text
        elif c.source_file:
            stem = c.source_file.rsplit(".", 1)[0]
            if stem in answer_text:
                keep = True

        if keep:
            used.append(c)

    return used if used else citations[:3]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, db: Session = Depends(get_db)):
    try:
        scope = resolve_scope(db, req.company_id, req.user_id)
    except ScopeError as e:
        raise HTTPException(status_code=403, detail=str(e))

    retrieval = route_query(db, req.query, scope)
    client = _get_sync_client()
    response = generate_answer(
        db,
        req.query,
        retrieval,
        client=client,
        user_display_name=scope.user_display_name,
    )
    response.citations = _filter_used_citations(
        response.citations, retrieval.chunks, response.answer
    )
    return response


@router.post("/search/stream")
def search_stream(req: SearchRequest, db: Session = Depends(get_db)):
    """SSE streaming — citations sent AFTER answer so we can filter."""
    try:
        scope = resolve_scope(db, req.company_id, req.user_id)
    except ScopeError as e:
        raise HTTPException(status_code=403, detail=str(e))

    retrieval = route_query(db, req.query, scope)
    classification = retrieval.classification

    async def event_stream():
        # 1. Thought trace
        trace = {
            "type": "trace",
            "intent": classification.intent,
            "strategy": classification.strategy,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "chunks_retrieved": len(retrieval.chunks),
            "structured_data": retrieval.structured is not None
            and not retrieval.structured.is_empty,
        }
        yield f"data: {json.dumps(trace)}\n\n"

        # 2. Stream answer tokens
        full_answer = ""
        client = _get_async_client()
        async for token in generate_answer_stream(
            db,
            req.query,
            retrieval,
            client=client,
            user_display_name=scope.user_display_name,
        ):
            full_answer += token
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

        # 3. Citations — filtered to only those the LLM used
        if classification.intent == QueryIntent.ASSIGNED_SEARCH and retrieval.chunks:
            all_citations = build_citations(db, retrieval.chunks)
            used = _filter_used_citations(all_citations, retrieval.chunks, full_answer)
            for c in used:
                yield f"data: {json.dumps({'type': 'citation', **c.model_dump()})}\n\n"

        # 4. Disclaimer
        if classification.intent == QueryIntent.GENERAL_PROFESSIONAL:
            from backend.app.core.guardrails import GENERAL_PROFESSIONAL_DISCLAIMER

            yield f"data: {json.dumps({'type': 'disclaimer', 'text': GENERAL_PROFESSIONAL_DISCLAIMER})}\n\n"

        # 5. Done
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

"""
Answer generator: produces the final response based on retrieval results.

Four paths:
  1. assigned_search  → LLM grounded answer from chunks/structured data + citations
  2. general_professional → LLM general answer + disclaimer
  3. out_of_scope → static guardrail message
  4. proprietary_ungrounded → static guardrail message
"""

from collections.abc import AsyncIterator
from pathlib import Path

import anthropic

from backend.app.api.schemas.search import Citation, SearchResponse, ThoughtTrace
from backend.app.core.citations import build_citations
from backend.app.core.guardrails import (
    GENERAL_PROFESSIONAL_DISCLAIMER,
    NO_RESULTS_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    PROPRIETARY_UNGROUNDED_RESPONSE,
)
from backend.app.core.retrieval_router import RetrievalResult
from backend.app.models.enums import QueryIntent, RetrievalStrategy
from backend.app.repositories.chunk_repo import ChunkResult
from backend.app.repositories.search_repo import StructuredResult
from sqlalchemy.orm import Session

_GROUNDED_PROMPT = Path("backend/app/prompts/grounded_answer.txt").read_text()


# ---------------------------------------------------------------------------
# Context builders — format retrieval results for the LLM
# ---------------------------------------------------------------------------


def _format_chunks_context(chunks: list[ChunkResult]) -> str:
    """Format chunks into labeled context blocks for the LLM.
    Groups by source type so the LLM can distinguish training vs history."""
    if not chunks:
        return ""

    training = []
    history = []

    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        chunk_type = meta.get("type", "")

        # Build source label
        if chunk_type == "page_text" or chunk_type == "section":
            page = meta.get("page", "?")
            label = f"[Source {i}: PDF Page {page}]"
        elif chunk_type == "table":
            page = meta.get("page", "?")
            title = meta.get("title", "Table")
            label = f"[Source {i}: {title}, Page {page}]"
        elif chunk_type == "segment":
            start = meta.get("start", "")
            end = meta.get("end", "")
            speaker = meta.get("speaker", "")
            label = f"[Source {i}: Video/Audio {start}-{end}"
            if speaker:
                label += f", Speaker: {speaker}"
            label += "]"
        elif chunk_type == "full_transcript":
            label = f"[Source {i}: Full Transcript]"
        elif chunk_type == "feedback":
            score = meta.get("score", "?")
            label = f"[Source {i}: Feedback, Score {score}/10]"
        elif chunk_type == "image":
            label = f"[Source {i}: Image Description]"
        else:
            label = f"[Source {i}]"

        entry = f"{label}\n{chunk.content}"

        if chunk.source_type == "history":
            history.append(entry)
        else:
            training.append(entry)

    parts = []
    if history:
        parts.append("=== USER HISTORY (your submissions & feedback) ===\n" + "\n\n".join(history))
    if training:
        parts.append("=== TRAINING MATERIALS ===\n" + "\n\n".join(training))

    return "\n\n".join(parts)


def _format_structured_context(structured: StructuredResult | None) -> str:
    """Format structured data into context for the LLM."""
    if not structured or structured.is_empty:
        return ""
    parts = []

    if structured.plays:
        parts.append("ASSIGNED PLAYS:")
        for p in structured.plays:
            parts.append(f"  - {p.title} (Status: {p.status})")

    if structured.submissions:
        parts.append("\nSUBMISSIONS:")
        for s in structured.submissions:
            parts.append(
                f"  - {s.rep_title} ({s.play_title}) — {s.submission_type}, "
                f"submitted {s.submitted_at}"
            )

    if structured.feedback:
        parts.append("\nFEEDBACK:")
        for f in structured.feedback:
            parts.append(f'  - {f.rep_title}: Score {f.score}/10 — "{f.text}"')

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Non-streaming answer (sync)
# ---------------------------------------------------------------------------


def generate_answer(
    db: Session,
    query: str,
    retrieval: RetrievalResult,
    client: anthropic.Anthropic | None = None,
    user_display_name: str = "",
) -> SearchResponse:
    """
    Generate the final answer. Uses LLM for assigned_search and general_professional.
    Returns static guardrail text for out_of_scope and proprietary_ungrounded.
    """
    classification = retrieval.classification
    intent = classification.intent

    trace = ThoughtTrace(
        intent=intent,
        strategy=classification.strategy,
        confidence=classification.confidence,
        reason=classification.reason,
        chunks_retrieved=len(retrieval.chunks),
        structured_data=retrieval.structured is not None and not retrieval.structured.is_empty,
    )

    # --- Static guardrail responses ---

    if intent == QueryIntent.OUT_OF_SCOPE:
        return SearchResponse(
            answer=OUT_OF_SCOPE_RESPONSE,
            citations=[],
            thought_trace=trace,
        )

    if intent == QueryIntent.PROPRIETARY_UNGROUNDED:
        return SearchResponse(
            answer=PROPRIETARY_UNGROUNDED_RESPONSE,
            citations=[],
            thought_trace=trace,
        )

    # --- General professional (LLM with disclaimer) ---

    if intent == QueryIntent.GENERAL_PROFESSIONAL:
        answer = _call_llm_general(query, client)
        return SearchResponse(
            answer=answer,
            citations=[],
            disclaimer=GENERAL_PROFESSIONAL_DISCLAIMER,
            thought_trace=trace,
        )

    # --- Assigned search (grounded answer) ---

    # Build context from retrieval results
    chunks_ctx = _format_chunks_context(retrieval.chunks)
    structured_ctx = _format_structured_context(retrieval.structured)

    context = ""
    if user_display_name:
        context += f"CURRENT USER: {user_display_name}\n"
        context += "Note: if the query references this user by name, treat it as a self-referential query.\n\n"
    if structured_ctx:
        context += "STRUCTURED DATA:\n" + structured_ctx + "\n\n"
    if chunks_ctx:
        context += "DOCUMENT CONTENT:\n" + chunks_ctx

    if not context.strip():
        return SearchResponse(
            answer=NO_RESULTS_RESPONSE,
            citations=[],
            thought_trace=trace,
        )

    # Build citations from chunks
    citations = build_citations(db, retrieval.chunks)

    answer = _call_llm_grounded(query, context, client)

    return SearchResponse(
        answer=answer,
        citations=citations,
        thought_trace=trace,
    )


# ---------------------------------------------------------------------------
# Streaming answer (async)
# ---------------------------------------------------------------------------


async def generate_answer_stream(
    db: Session,
    query: str,
    retrieval: RetrievalResult,
    client: anthropic.AsyncAnthropic | None = None,
    user_display_name: str = "",
) -> AsyncIterator[str]:
    """
    Stream the answer token-by-token.
    Yields text chunks. Non-LLM responses yield the full text in one chunk.
    """
    classification = retrieval.classification
    intent = classification.intent

    # Static responses — yield all at once
    if intent == QueryIntent.OUT_OF_SCOPE:
        yield OUT_OF_SCOPE_RESPONSE
        return

    if intent == QueryIntent.PROPRIETARY_UNGROUNDED:
        yield PROPRIETARY_UNGROUNDED_RESPONSE
        return

    # General professional — stream from LLM
    if intent == QueryIntent.GENERAL_PROFESSIONAL:
        async for token in _stream_llm_general(query, client):
            yield token
        return

    # Assigned search — stream grounded answer
    chunks_ctx = _format_chunks_context(retrieval.chunks)
    structured_ctx = _format_structured_context(retrieval.structured)

    context = ""
    if user_display_name:
        context += f"CURRENT USER: {user_display_name}\n"
        context += "Note: if the query references this user by name, treat it as a self-referential query.\n\n"
    if structured_ctx:
        context += "STRUCTURED DATA:\n" + structured_ctx + "\n\n"
    if chunks_ctx:
        context += "DOCUMENT CONTENT:\n" + chunks_ctx

    if not context.strip():
        yield NO_RESULTS_RESPONSE
        return

    async for token in _stream_llm_grounded(query, context, client):
        yield token


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------


def _call_llm_grounded(
    query: str,
    context: str,
    client: anthropic.Anthropic | None,
) -> str:
    """Sync grounded answer from LLM."""
    if client is None:
        # Fallback: return context summary without LLM
        return f"Based on your assigned materials:\n\n{context[:2000]}"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=_GROUNDED_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuery: {query}",
            }
        ],
    )
    return response.content[0].text


def _call_llm_general(
    query: str,
    client: anthropic.Anthropic | None,
) -> str:
    """Sync general professional answer from LLM."""
    if client is None:
        return (
            "I can help with general sales knowledge. However, I don't have access "
            "to an LLM client right now. Please configure your API key."
        )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=(
            "You are a helpful sales training assistant. Provide practical, "
            "actionable advice based on general sales knowledge. Be concise."
        ),
        messages=[{"role": "user", "content": query}],
    )
    return response.content[0].text


async def _stream_llm_grounded(
    query: str,
    context: str,
    client: anthropic.AsyncAnthropic | None,
) -> AsyncIterator[str]:
    """Stream grounded answer tokens."""
    if client is None:
        yield f"Based on your assigned materials:\n\n{context[:2000]}"
        return

    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=_GROUNDED_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuery: {query}",
            }
        ],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _stream_llm_general(
    query: str,
    client: anthropic.AsyncAnthropic | None,
) -> AsyncIterator[str]:
    """Stream general professional answer tokens."""
    if client is None:
        yield (
            "I can help with general sales knowledge. However, I don't have access "
            "to an LLM client right now. Please configure your API key."
        )
        return

    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=(
            "You are a helpful sales training assistant. Provide practical, "
            "actionable advice based on general sales knowledge. Be concise."
        ),
        messages=[{"role": "user", "content": query}],
    ) as stream:
        async for text in stream.text_stream:
            yield text

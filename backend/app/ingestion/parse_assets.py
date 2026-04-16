"""
Parse asset JSON files into paragraph-level chunks for hybrid search.

Chunking strategy:
  - PDF: one chunk per page (sections + tables merged into page context)
  - Video/Audio: group segments into ~3-5 sentence paragraphs, keep timestamps
  - Image: single chunk (alt_text + ocr_text)
  - Text: single chunk
  - Feedback: single chunk (handled in build_chunks.py)

Target chunk size: 200-800 chars (~50-200 tokens). Big enough for
meaningful embeddings, small enough for precise retrieval.
"""

import json
from pathlib import Path


def _load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# PDF: one chunk per page, combining sections + tables into rich context
# ---------------------------------------------------------------------------


def parse_pdf(path: Path) -> list[dict]:
    pages = _load_json(path)
    chunks = []
    for page in pages:
        page_num = page["page"]

        # Build a single rich page chunk from sections + tables
        parts = []

        for sec in page.get("sections", []):
            heading = sec.get("heading", "")
            content = sec.get("content", "").strip()
            if content:
                parts.append(f"{heading}: {content}" if heading else content)

        for tbl in page.get("tables", []):
            headers = tbl.get("headers", [])
            rows_text = []
            for row in tbl.get("rows", []):
                row_str = " | ".join(f"{h}: {v}" for h, v in zip(headers, row))
                rows_text.append(row_str)
            title = tbl.get("title", "Table")
            table_text = f"{title}.\n" + "\n".join(rows_text)
            parts.append(table_text)

        if parts:
            # Combined page chunk with sections + tables
            chunks.append(
                {
                    "content": "\n\n".join(parts).strip(),
                    "metadata": {"page": page_num, "type": "page_text"},
                }
            )
        elif page.get("text", "").strip():
            # Fallback: raw page text if no sections/tables
            chunks.append(
                {
                    "content": page["text"].strip(),
                    "metadata": {"page": page_num, "type": "page_text"},
                }
            )

        # Also create separate table chunks for precise table retrieval
        for tbl in page.get("tables", []):
            headers = tbl.get("headers", [])
            rows_text = []
            for row in tbl.get("rows", []):
                row_str = " | ".join(f"{h}: {v}" for h, v in zip(headers, row))
                rows_text.append(row_str)
            content = f"{tbl.get('title', 'Table')}.\n" + "\n".join(rows_text)
            chunks.append(
                {
                    "content": content.strip(),
                    "metadata": {
                        "page": page_num,
                        "table_id": tbl.get("id"),
                        "title": tbl.get("title", ""),
                        "type": "table",
                    },
                }
            )

    return chunks


# ---------------------------------------------------------------------------
# Video / Audio: group segments into paragraphs of ~3-5 sentences
# ---------------------------------------------------------------------------

SEGMENTS_PER_PARAGRAPH = 4


def parse_transcript(path: Path) -> list[dict]:
    data = _load_json(path)
    chunks = []

    # Full transcript as a single chunk (broad matching)
    full = data.get("full_transcript", "").strip()
    if full:
        chunks.append(
            {
                "content": full,
                "metadata": {"type": "full_transcript"},
            }
        )

    # Group segments into paragraph-sized chunks
    segments = data.get("segments", [])
    for i in range(0, len(segments), SEGMENTS_PER_PARAGRAPH):
        group = segments[i : i + SEGMENTS_PER_PARAGRAPH]
        texts = [s.get("text", "").strip() for s in group if s.get("text", "").strip()]
        if not texts:
            continue

        content = " ".join(texts)
        start = group[0].get("start")
        end = group[-1].get("end")
        speakers = list({s.get("speaker", "") for s in group if s.get("speaker")})

        chunks.append(
            {
                "content": content,
                "metadata": {
                    "start": start,
                    "end": end,
                    "speaker": speakers[0] if len(speakers) == 1 else ", ".join(speakers),
                    "type": "segment",
                },
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# Image: combine alt_text + ocr_text into one chunk
# ---------------------------------------------------------------------------


def parse_image(path: Path) -> list[dict]:
    data = _load_json(path)
    parts = []
    if data.get("alt_text"):
        parts.append(data["alt_text"])
    if data.get("ocr_text"):
        parts.append(data["ocr_text"])
    if not parts:
        return []
    return [
        {
            "content": "\n".join(parts).strip(),
            "metadata": {
                "tags": data.get("tags", []),
                "type": "image",
            },
        }
    ]


# ---------------------------------------------------------------------------
# Text: full_text as a single chunk
# ---------------------------------------------------------------------------


def parse_text(path: Path) -> list[dict]:
    data = _load_json(path)
    text = data.get("full_text", "").strip()
    if not text:
        return []
    return [
        {
            "content": text,
            "metadata": {"type": "full_text"},
        }
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    "pdf": parse_pdf,
    "video": parse_transcript,
    "audio": parse_transcript,
    "image": parse_image,
    "text": parse_text,
}


def parse_asset(asset_type: str, path: Path) -> list[dict]:
    parser = PARSERS.get(asset_type)
    if parser is None:
        print(f"  ⚠ No parser for asset type '{asset_type}', skipping")
        return []
    return parser(path)

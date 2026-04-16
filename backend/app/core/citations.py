"""
Build Citation objects from chunk metadata + asset lookup.

Citation formats:
  PDF:   [PDF: amproxin_guide.pdf, Page 1]
  Video: [Video: synthetic_sinew_demo.mp4, 00:26 - 00:38]
  Audio: [Audio: kyb_user_sub_1.mp3, 00:10 - 00:22]
  Image: [Image: neuro_linker_diagram.png]
  Text:  [Text: submission transcript]
  Feedback: [Feedback: score 8/10]
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.schemas.search import Citation
from backend.app.repositories.chunk_repo import ChunkResult

# file_name in DB is .json — map to original extension for display
_TYPE_EXT = {
    "pdf": "pdf",
    "video": "mp4",
    "audio": "mp3",
    "image": "png",
    "text": "txt",
}


def _load_asset_names(db: Session, asset_ids: set[str]) -> dict[str, tuple[str, str]]:
    """Returns {asset_id: (display_filename, asset_type)}."""
    if not asset_ids:
        return {}
    rows = db.execute(
        text("SELECT id, type, file_name FROM assets WHERE id = ANY(:ids)"),
        {"ids": list(asset_ids)},
    ).all()
    result = {}
    for aid, atype, fname in rows:
        ext = _TYPE_EXT.get(atype, "txt")
        display = fname.replace(".json", f".{ext}")
        result[aid] = (display, atype)
    return result


def _dedup_key(citation: Citation) -> str:
    """Key for deduplication — group by source file + location."""
    if citation.source_type == "pdf":
        return f"{citation.source_file}:p{citation.page}"
    if citation.source_type in ("video", "audio"):
        if citation.start:
            return f"{citation.source_file}:{citation.start}-{citation.end}"
        return f"{citation.source_file}:full"
    if citation.source_type == "feedback":
        return citation.label
    return f"{citation.source_file}:{citation.source_type}"


def build_citations(db: Session, chunks: list[ChunkResult]) -> list[Citation]:
    """Build Citation objects from retrieved chunks, deduplicating by source location."""
    asset_ids = {c.asset_id for c in chunks if c.asset_id}
    asset_names = _load_asset_names(db, asset_ids)

    seen_keys = set()
    citations = []

    for chunk in chunks:
        meta = chunk.metadata
        chunk_type = meta.get("type", "")
        asset_id = chunk.asset_id

        if asset_id and asset_id in asset_names:
            display_name, asset_type = asset_names[asset_id]
        else:
            display_name = "unknown"
            asset_type = "text"

        citation = _build_one(display_name, asset_type, chunk_type, meta, asset_id)
        if citation:
            key = _dedup_key(citation)
            if key not in seen_keys:
                seen_keys.add(key)
                citations.append(citation)

    # Remove "full transcript" citations when specific timestamps exist for same file
    files_with_timestamps = {
        c.source_file for c in citations if c.source_type in ("video", "audio") and c.start
    }
    citations = [
        c
        for c in citations
        if not (
            c.source_type in ("video", "audio")
            and not c.start
            and c.source_file in files_with_timestamps
        )
    ]

    return citations


def _build_one(
    display_name: str,
    asset_type: str,
    chunk_type: str,
    meta: dict,
    asset_id: str | None = None,
) -> Citation | None:
    """Build a single Citation based on asset type and chunk metadata."""

    # Feedback chunk
    if chunk_type == "feedback":
        score = meta.get("score", "?")
        return Citation(
            source_file=display_name,
            source_type="feedback",
            label=f"[Feedback: score {score}/10]",
            asset_id=asset_id,
        )

    # PDF
    if asset_type == "pdf":
        page = meta.get("page")
        section = meta.get("heading")
        if page:
            label = f"[PDF: {display_name}, Page {page}]"
            if section:
                label = f"[PDF: {display_name}, Page {page} — {section}]"
        else:
            label = f"[PDF: {display_name}]"
        return Citation(
            source_file=display_name,
            source_type="pdf",
            label=label,
            asset_id=asset_id,
            page=int(page) if page else None,
            section=section,
        )

    # Video
    if asset_type == "video":
        start = meta.get("start")
        end = meta.get("end")
        if start and end:
            label = f"[Video: {display_name}, {start} - {end}]"
        else:
            label = f"[Video: {display_name}]"
        return Citation(
            source_file=display_name,
            source_type="video",
            label=label,
            asset_id=asset_id,
            start=start,
            end=end,
        )

    # Audio
    if asset_type == "audio":
        start = meta.get("start")
        end = meta.get("end")
        if start and end:
            label = f"[Audio: {display_name}, {start} - {end}]"
        else:
            label = f"[Audio: {display_name}]"
        return Citation(
            source_file=display_name,
            source_type="audio",
            label=label,
            asset_id=asset_id,
            start=start,
            end=end,
        )

    # Image
    if asset_type == "image":
        return Citation(
            source_file=display_name,
            source_type="image",
            label=f"[Image: {display_name}]",
            asset_id=asset_id,
        )

    # Text / submission transcript
    return Citation(
        source_file=display_name,
        source_type="text",
        label=f"[Text: {display_name}]",
        asset_id=asset_id,
    )

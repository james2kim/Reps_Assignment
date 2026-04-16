"""
Generate embeddings for all search_chunks and store in the embedding column.

Uses sentence-transformers all-MiniLM-L6-v2 (384 dimensions).
Processes in batches for efficiency.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.session import SessionLocal

BATCH_SIZE = 64


def _get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed_all(db: Session | None = None) -> int:
    """Embed all chunks that don't have embeddings yet."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # Get chunks without embeddings
        rows = db.execute(
            text("SELECT id, content FROM search_chunks WHERE embedding IS NULL")
        ).all()

        if not rows:
            print("  All chunks already embedded.")
            return 0

        print(f"  Embedding {len(rows)} chunks...")
        model = _get_model()

        # Process in batches
        total = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            ids = [r[0] for r in batch]
            texts = [r[1] for r in batch]

            embeddings = model.encode(texts, show_progress_bar=False)

            for chunk_id, emb in zip(ids, embeddings):
                db.execute(
                    text("UPDATE search_chunks SET embedding = :emb WHERE id = :id"),
                    {"id": chunk_id, "emb": emb.tolist()},
                )

            total += len(batch)
            print(f"    {total}/{len(rows)} chunks embedded")

        db.commit()
        print(f"  Done. {total} embeddings generated.")
        return total
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    print("Embedding search chunks...")
    embed_all()

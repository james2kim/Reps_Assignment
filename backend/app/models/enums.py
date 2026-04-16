from enum import StrEnum


class AssetType(StrEnum):
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    TEXT = "text"
    FLASHCARD = "flashcard"


class RepType(StrEnum):
    WATCH = "watch"
    PRACTICE = "practice"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SubmissionType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


class QueryIntent(StrEnum):
    ASSIGNED_SEARCH = "assigned_search"
    GENERAL_PROFESSIONAL = "general_professional"
    OUT_OF_SCOPE = "out_of_scope"
    PROPRIETARY_UNGROUNDED = "proprietary_ungrounded"


class RetrievalStrategy(StrEnum):
    STRUCTURED = "structured"  # answer from relational tables
    DOCUMENT = "document"  # answer from chunk content (RAG)
    HYBRID = "hybrid"  # both structured facts + document grounding
    NONE = "none"  # no retrieval needed


class ChunkSource(StrEnum):
    ASSET = "asset"
    HISTORY = "history"

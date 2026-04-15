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
    PRODUCT_KNOWLEDGE = "product_knowledge"
    SUBMISSION_REVIEW = "submission_review"
    FEEDBACK_LOOKUP = "feedback_lookup"
    GENERAL = "general"


class ChunkSource(StrEnum):
    ASSET = "asset"
    SUBMISSION = "submission"
    FEEDBACK = "feedback"

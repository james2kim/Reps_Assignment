from pydantic import BaseModel


class SearchScope(BaseModel):
    """The complete set of IDs a user is authorized to search."""

    company_id: str
    user_id: str
    allowed_play_ids: set[str]
    allowed_rep_ids: set[str]
    allowed_asset_ids: set[str]
    allowed_submission_ids: set[str]
    allowed_feedback_ids: set[str]
    play_titles: list[str] = []  # for classifier context
    user_display_name: str = ""  # for LLM context ("Aaron Montgomery")

    @property
    def is_empty(self) -> bool:
        return not self.allowed_asset_ids and not self.allowed_submission_ids

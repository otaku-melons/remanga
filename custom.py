from pydantic import BaseModel

class CustomSettingsModel(BaseModel):
	"""Custom parser settings model."""

	token: str | None
	add_free_publication_date: bool
	only_best_cover: bool

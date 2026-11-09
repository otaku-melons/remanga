from typing import Annotated

from pydantic import BaseModel

from dublib.validators import types

class ExMangaModel(BaseModel):
	"""ExManga model."""

	email: str | None = None
	password: str | None = None
	domain: Annotated[str, types.Domain] = "exmanga.org"

class CustomSettingsModel(BaseModel):
	"""Custom parser settings model."""

	token: str | None
	add_free_publication_date: bool
	only_best_cover: bool
	exmanga: ExMangaModel = ExMangaModel()

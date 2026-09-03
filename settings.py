from pydantic.dataclasses import dataclass

from melon.core.base.parsers.components.settings import CustomSettingsTemplate

@dataclass(frozen = True)
class CustomSettingsModel(CustomSettingsTemplate):
	"""Кастомные параметры парсера."""

	token: str | None
	add_free_publication_date: bool
	only_best_cover: bool

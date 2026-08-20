from dataclasses import dataclass

@dataclass(frozen = True)
class TitleIdentificators:
	"""Идентификаторы тайтла."""

	id: int
	slug: str
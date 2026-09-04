from pydantic.dataclasses import dataclass

from melon.core.base.parsers.components.settings import BaseExtensionOptions

@dataclass(frozen = True)
class Options(BaseExtensionOptions):
	"""Опции расширения."""

	token: str
	domain: str = "exmanga.org"

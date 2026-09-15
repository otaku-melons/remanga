from pydantic.dataclasses import dataclass

from melon.core.base.parsers.components.settings import BaseExtensionOptions

@dataclass(frozen = True)
class Options(BaseExtensionOptions):
	"""Опции расширения."""

	email: str
	password: str
	use_mirror: bool = False

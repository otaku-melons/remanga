from pydantic.dataclasses import dataclass

from melon.core.base.extensions.options import BaseExtensionOptions

@dataclass(frozen = True)
class Options(BaseExtensionOptions):
	"""Опции расширения."""

	query: str = "img{r:1-6}{ov:-reserve}.reimg{ov:2}.org"

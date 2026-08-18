from typing import cast

from melon.core.base.parsers.components.settings import BaseExtensionOptions

class Options(BaseExtensionOptions):
	"""Опции расширения."""

	@property
	def domain(self) -> str:
		"""Домен сервера."""

		return self._Data.get("domain") or "exmanga.org"

	@property
	def token(self) -> str | None:
		"""Токен авторизации."""

		Value: str | None = self.get("token")
		if not Value: return None
		Value = cast(str, Value)

		if Value.lower().startswith("berarer "):
			Value = Value[:len("berarer ") * -1]

		return Value

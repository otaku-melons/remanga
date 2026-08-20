from melon.core.base.parsers.components.settings import BaseExtensionOptions

class Options(BaseExtensionOptions):
	"""Опции расширения."""

	@property
	def run_on_not_found_error(self) -> bool:
		"""
		Состояние: следует ли попытаться обновить алиас при ошибке получения тайтла с кодом 404.

		Если расширение отключено, вернёт `False`.
		"""

		return all((self.get("run_on_not_found_error"), self.is_enabled))
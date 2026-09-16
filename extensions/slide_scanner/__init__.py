from typing import TYPE_CHECKING, override

from melon.core.base.extensions import BaseExtension

from .cli import CLI
from .options import Options

if TYPE_CHECKING:
	from ... import SourceOperator as SourceOperator

class Extension(BaseExtension["SourceOperator", "Options"]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	@override
	def _export_options_model(self) -> type[Options]:
		"""
		Возвращает модель опций.

		:return: Модель опций.
		:rtype: type[BaseExtensionOptions]
		"""

		return Options

	@override
	def _provide_cli(self) -> type[CLI]:
		"""
		Возвращает класс-обработчик CLI.

		:return: Класс-обработчик CLI.
		:rtype: type[CLI]
		"""

		return CLI

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#


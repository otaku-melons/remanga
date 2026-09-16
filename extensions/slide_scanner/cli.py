from typing import TYPE_CHECKING

from melon.core.base.extensions.cli import BaseExtensionCLI

if TYPE_CHECKING:
	from dublib.cli.terminalyzer import ModelsGroup
	from dublib.cli.terminalyzer.parser.entitites import CommandEntity

	from . import Extension as Extension

class CLI(BaseExtensionCLI["Extension"]):
	"""Оператор CLI."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ ОБРАБОТЧИКИ КОМАНД <<<<< #
	#==========================================================================================#

	def __any_handler(self, entity: "CommandEntity"):  # noqa: ARG002

		print("Hello, handler!")
		
	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _command_not_found(self):
		"""Обрабатывает отсутствие соответствующей параметром команды."""

		pass

	def _build_models_group(self, group: "ModelsGroup"):
		"""
		Строит модели команд.

		:param group: Группа, к которой должны принадлежать модели команд.
		:type group: ModelsGroup
		"""

		model = group.create_model("any")
		model.register_handler(self.__any_handler)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from melon.core.base.parser.components.manifest import ParserManifest
	from melon.core.system_objects.printer import Portals, SystemObjects

	from .. import SourceOperator as SourceOperator

class BaseModule:
	"""Base extension-like module."""

	def __init__(self, source_operator: "SourceOperator"):
		"""
		ExManga slides receiver..

		Args:
			source_operator (SourceOperator): Source operator.
		"""

		self.__source_operator: SourceOperator = source_operator

		self._post_init()

	def _post_init(self):
		"""Execute after instance initialization."""

		pass

	@property
	def manifest(self) -> "ParserManifest":
		"""Parser manifest."""

		return self.__source_operator.manifest

	@property
	def portals(self) -> "Portals":
		"""Output portals."""

		return self.__source_operator.portals

	@property
	def source_operator(self) -> "SourceOperator":
		"""Source operator."""

		return self.__source_operator

	@property
	def system_objects(self) -> "SystemObjects":
		"""System objects collection."""

		return self.__source_operator.system_objects

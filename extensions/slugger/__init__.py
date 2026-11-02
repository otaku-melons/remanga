from typing import TYPE_CHECKING

from melon.core.base.extensions import BaseExtension
from melon.core.base.structs.title import TitleDescriptor

if TYPE_CHECKING:
	from melon.core.base.formats.base_format.data import BaseTitleData

	from ... import SourceOperator as SourceOperator

class Extension(BaseExtension["SourceOperator"]):
	"""Title slug updater."""

	def __search_by_name(self, name: str) -> list[TitleDescriptor]:
		"""
		Получает до 10 тайтлов методом поиска в каталоге по названию.

		:param name: Название тайтла.
		:type name: str
		:return: Список идентификаторов тайтла.
		:rtype: list[TitleDescriptor]
		"""

		Params: dict = {
			"count": "10",
			"field": "titles",
			"page": "1",
			"query": name,
		}
		Response = self.source_operator.requestor.get(f"https://{self.source_operator.manifest.domain}/api/v2/search/", params = Params)
		if Response.ok and Response.json:
			Results: list[dict] = Response.json["results"]
			return self.__search_results_to_structs(Results)

		else: self.source_operator.portals.request_error(Response, "Search by name failed.")

		return []

	def __search_results_to_structs(self, results: list[dict]) -> list[TitleDescriptor]:
		"""
		Преобразует список результатов поиска в идентификаторы тайтлов.

		:param results: Список результатов поиска.
		:type results: list[dict]
		:return: Список идентификаторов тайтлов.
		:rtype: list[TitleDescriptor]
		"""

		Identifiers: list[TitleDescriptor] = []

		for Data in results:
			ID: int = Data["id"]
			Slug: str = Data["dir"]
			Buffer = TitleDescriptor(self.source_operator)
			Buffer.set_id(ID)
			Buffer.set_slug(Slug)
			Identifiers.append(Buffer)

		return Identifiers

	def get_title_descriptor_by_name(self, data: "BaseTitleData") -> TitleDescriptor | None:
		"""
		GEt title descriptor by name.

		Args:
			data (BaseTitleData): Title data.

		Raises:
			ValueError: Missing title ID or localized name.

		Returns:
			TitleDescriptor | None: Title descriptor or `None` if not found.
		"""

		if not data.id:
			raise ValueError("Title must have ID for this operation.")

		if not data.localized_name:
			raise ValueError("Title must have localized name for this operation.")

		for Descriptor in self.__search_by_name(data.localized_name):
			if data.id == Descriptor.id:
				return Descriptor

	def update_title_slug(self, data: "BaseTitleData") -> bool:
		"""
		Try to title slug.

		Args:
			data (BaseTitleData): Title data.

		Returns:
			bool: `True` if title slug changed.
		"""

		descriptor: TitleDescriptor | None = self.get_title_descriptor_by_name(data)

		if not descriptor or not descriptor.slug or not descriptor.id:
			return False

		if data.slug != descriptor.slug:
			data.set_slug(descriptor.slug)
			self.source_operator.shared_data.journal.update(descriptor.id, descriptor.slug)
			self.portals.printer.emit(f"Slug updated: <i>{descriptor.slug}</i>.")
			return True

		return False

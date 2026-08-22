from melon.core.base.extensions import BaseExtension, BaseExtensionOptions
from melon.core.base.formats.base_format import BaseTitle
from melon.core.structs import TitleDescriptor

class Extension(BaseExtension[BaseExtensionOptions]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __SearchByName(self, name: str) -> list[TitleDescriptor]:
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
			"query": name
		}
		Response = self.source_operator.requestor.get(f"https://{self.source_operator.manifest.domain}/api/v2/search/", params = Params)
		if Response.ok and Response.json:
			Results: list[dict] = Response.json["results"]
			return self.__SearchResultsToStructs(Results)

		else: self.source_operator.portals.request_error(Response, "Search by name failed.")

		return []

	def __SearchResultsToStructs(self, results: list[dict]) -> list[TitleDescriptor]:
		"""
		Преобразует список результатов поиска в идентификаторы тайтлов.

		:param results: Список результатов поиска.
		:type results: list[dict]
		:return: Список идентификаторов тайтлов.
		:rtype: list[TitleDescriptor]
		"""

		Identificators: list[TitleDescriptor] = []

		for Data in results:
			ID: int = Data["id"]
			Slug: str = Data["dir"]
			Buffer = TitleDescriptor(self.source_operator)
			Buffer.set_id(ID)
			Buffer.set_slug(Slug)
			Identificators.append(Buffer)

		return Identificators

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _ReturnOptionsType(self) -> type[BaseExtensionOptions]:
		"""
		Возвращает тип контейнера опций.

		:return: Тип контейнера опций.
		:rtype: type[T]
		"""

		return BaseExtensionOptions

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def get_title_descriptor_by_name(self, title: "BaseTitle") -> TitleDescriptor | None:
		"""
		Пытается получить дескриптор тайтла методом поиска по названию.

		:param title: Тайтл.
		:type title: BaseTitle
		:raises ValueError: В тайтле не заполнены обязательные поля.
		:return: Дескриптор тайтла или `None` при неудаче.
		:rtype: TitleDescriptor | None
		"""

		if not title.id:
			raise ValueError("Title must have ID for this operation.")

		if not title.localized_name:
			raise ValueError("Title must have localized name for this operation.")

		for Descriptor in self.__SearchByName(title.localized_name):
			if title.id == Descriptor.id:
				return Descriptor

		return None

	def update_title_slug(self, title: "BaseTitle") -> bool:
		"""
		Обновляет алиас тайтла, пытаясь обнаружить название последнего в каталоге и сравнить ID.

		:param title: Тайтл.
		:type title: BaseTitle
		:raises ValueError: В тайтле не заполнены обязательные поля.
		:return: Возвращает `True`, если алиас тайтла изменился.
		:rtype: bool
		"""

		Descriptor: TitleDescriptor | None = self.get_title_descriptor_by_name(title)

		if not Descriptor or not Descriptor.slug or not Descriptor.id:
			return False
		
		if title.slug != Descriptor.slug:
			title.set_slug(Descriptor.slug)
			self.source_operator.shared_data.journal.update(Descriptor.id, Descriptor.slug)
			self.portals.printer.emit(f"Slug updated: <i>{Descriptor.slug}</i>.")
			return True

		return False

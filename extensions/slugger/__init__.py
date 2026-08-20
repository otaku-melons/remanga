from melon.core.base.extensions import BaseExtension
from melon.core.base.formats.base_format import BaseTitle

from .options import Options
from .structs import TitleIdentificators

class Extension(BaseExtension[Options]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __SearchByName(self, name: str) -> list[TitleIdentificators]:
		"""
		Получает до 10 тайтлов методом поиска в каталоге по названию.

		:param name: Название тайтла.
		:type name: str
		:return: Список идентификаторов тайтла.
		:rtype: list[TitleIdentificators]
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

	def __SearchResultsToStructs(self, results: list[dict]) -> list[TitleIdentificators]:
		"""
		Преобразует список результатов поиска в идентификаторы тайтлов.

		:param results: Список результатов поиска.
		:type results: list[dict]
		:return: Список идентификаторов тайтлов.
		:rtype: list[TitleIdentificators]
		"""

		Identificators: list[TitleIdentificators] = []

		for Data in results:
			ID: int = Data["id"]
			Slug: str = Data["dir"]
			Buffer = TitleIdentificators(ID, Slug)
			Identificators.append(Buffer)

		return Identificators

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _ReturnOptionsType(self) -> type[Options]:
		"""
		Возвращает тип контейнера опций.

		:return: Тип контейнера опций.
		:rtype: type[T]
		"""

		return Options

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def get_title_slug_by_name(self, title: "BaseTitle") -> TitleIdentificators | None:
		"""
		Пытается получить идентификаторы тайтла методом поиска по названию.

		:param title: Тайтл.
		:type title: BaseTitle
		:raises ValueError: В тайтле не заполнены обязательные поля.
		:return: Идентификаторы тайтла или `None` при неудаче.
		:rtype: TitleIdentificators | None
		"""

		if not title.id:
			raise ValueError("Title must have ID for this operation.")

		if not title.localized_name:
			raise ValueError("Title must have localized name for this operation.")

		for CurrentIdentificators in self.__SearchByName(title.localized_name):
			if title.id == CurrentIdentificators.id:
				return CurrentIdentificators

		return None

	def update_title_slug(self, title: "BaseTitle") -> bool:
		"""
		Обновляет алиас тайтла, пытаясь обнаружить название последнего в каталоге и сравнить ID.

		:param title: Тайтл.
		:type title: BaseTitle
		:param identificators: Идентификаторы тайтла.
		:type identificators: TitleIdentificators
		:raises ValueError: В тайтле не заполнены обязательные поля.
		:return: Возвращает `True`, если алиас тайтла изменился.
		:rtype: bool
		"""

		Identificators: TitleIdentificators | None = self.get_title_slug_by_name(title)

		if not Identificators:
			return False
		
		if title.slug != Identificators.slug:
			title.set_slug(Identificators.slug)
			self.source_operator.shared_data.journal.update(Identificators.id, Identificators.slug)
			self.portals.printer.emit(f"Slug updated: <i>{Identificators.slug}</i>.")
			return True

		return False

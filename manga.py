from typing import TYPE_CHECKING, cast, override

from dublib.functions.data import zerotify
from dublib.functions.data.string import remove_recurring_substrings
from dublib.polyglot import HTML
from dublib.web_requestor import WebResponse

from melon.core.base.formats.base_format.branch import Branch
from melon.core.base.formats.base_format.enums import Statuses
from melon.core.base.formats.base_format.person import Person
from melon.core.base.formats.manga.chapter import Chapter
from melon.core.base.formats.manga.controller import Manga
from melon.core.base.formats.manga.enums import Types
from melon.core.base.parsers.manga import BaseMangaParser
from melon.core.base.structs.image import ImageData

from . import extensions
from .functions import MergeLists

if TYPE_CHECKING:
	from . import SourceOperator as SourceOperator
	from .settings import CustomSettingsModel as CustomSettingsModel

class Parser(BaseMangaParser["SourceOperator", "CustomSettingsModel"]):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#
	
	@override
	def _amend(self, branch: Branch, chapter: Chapter) -> str | None:
		"""
		Дополняет главу дайными о контенте.

		:param branch: Ветвь.
		:type branch: Branch
		:param chapter: Глава.
		:type chapter: Chapter
		:return: Дополнительное необязательное сообщение о дополнении.
		:rtype: str | None
		"""

		Slides: list[ImageData] = self.__get_slides(chapter)
		Message: str | None = None
		self.source_operator.settings.custom
		
		if Slides:
			FirstSlideLink: str = Slides[0].link

			if FirstSlideLink.startswith("file:") or self.__ExManga.options.domain in FirstSlideLink:
				Message = "Received from ExManga."

			chapter.set_slides(Slides)

		return Message

	@override
	def _parse(self):
		"""Получает основные данные тайтла."""

		Title = cast(Manga, self.title)
		Response = self._get_title_data()

		if Response.ok and Response.json:
			Data = Response.json
			
			Title.data.set_id(Data["id"])
			Title.data.set_content_language("rus")
			Title.data.set_localized_name(Data["main_name"])
			Title.data.set_eng_name(Data["secondary_name"])
			Title.data.set_another_names(Data["another_name"].split(" / "))
			self._get_covers(Data)
			Title.data.set_publication_year(Data["issue_year"])
			Title.data.set_description(self._get_description(Data))
			Title.data.set_age_limit(self._get_age_limit(Data))
			Title.data.set_title_type(self.__get_type(Data))
			Title.data.set_status(self._get_status(Data))
			Title.data.set_is_licensed(Data["is_licensed"])
			Title.data.set_genres(self._get_genres(Data))
			Title.data.set_tags(self._get_tags(Data))
			Title.data.set_persons(self._get_persons())
			self.__get_branches(Data)

		elif Response.status_code == 404: self.portals.title_not_found(Title.data)
		else: self.portals.request_error(Response, "Unable to request title data.")

	@override
	def _post_init(self):
		"""Метод, выполняющийся после инициализации объекта."""
	
		self._IsPaidChaptersLocked = False

		self.__ExManga = self.source_operator.extensions.run(extensions.ExManga)
		self.__Slugger = self.source_operator.extensions.run(extensions.Slugger)

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def __get_branches(self, data: dict):
		"""
		Получает ветви тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		"""

		Title = cast(Manga, self.title)

		for CurrentBranchData in data["branches"]:
			BranchID = CurrentBranchData["id"]
			CurrentBranch = Branch(BranchID)
			BranchPage = 1

			while True:
				Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/chapters/?branch_id={BranchID}&ordering=-index&page={BranchPage}")
				BranchPage += 1
				
				if Response.ok and Response.json:
					Data = Response.json["results"]
					if not Data: break

					for CurrentChapter in Data:
						Translators = [sub["name"] for sub in CurrentChapter["publishers"]]
						Name: str | None = CurrentChapter["name"] if CurrentChapter["name"] != "null" else None

						Buffer = Chapter(self, CurrentChapter["id"])
						Buffer.set_volume(CurrentChapter["tome"])
						Buffer.set_number(CurrentChapter["chapter"])
						Buffer.set_name(Name)
						Buffer.set_is_paid(CurrentChapter["is_paid"])
						Buffer.set_workers(Translators)

						if self.settings.custom.add_free_publication_date and Buffer.is_paid:
							Buffer.extra_data.set("free-publication-date", CurrentChapter["pub_date"])
						
						CurrentBranch.add_chapter(Buffer)

				else:
					self.portals.request_error(Response, "Unable to request chapter.", exception = False)

			CurrentBranch.reverse()
			Title.data.add_branch(CurrentBranch)	

	def __get_slides(self, chapter: Chapter) -> list[ImageData]:
		"""
		Получает данные о слайдах главы.

		:param chapter: Глава.
		:type chapter: Chapter
		:return: Список данных слайдов.
		:rtype: list[ImageData]
		"""

		Slides: list[ImageData] = []

		if chapter.is_paid and self._IsPaidChaptersLocked:
			self.portals.chapter_skipped(chapter)
			return Slides

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/chapters/{chapter.id}/")

		if Response.ok and Response.json:
			Data = Response.json
			SlidesData: list[dict] = MergeLists(Data["pages"])

			if not SlidesData:
				Slides = self.__try_get_chapter_from_exmanga(chapter.id)
				if Slides: return Slides

				if chapter.is_paid:
					self._IsPaidChaptersLocked = True
					self.portals.printer.debug("Paid chapters locked. All will be skipped.")

				self.portals.chapter_skipped(chapter)
				return []
			
			for SlideData in SlidesData:
				Link = SlideData["link"]
				Width, Height = SlideData["width"], SlideData["height"]
				Buffer = ImageData(Link)
				Buffer.create_resolution(Width, Height)
				Slides.append(Buffer)

		else: self.portals.request_error(Response, "Unable to request chapter content.", exception = False)

		return Slides

	def __get_type(self, data: dict) -> Types | None:
		"""
		Определяет тип тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Тип тайтла.
		:rtype: Types | None
		"""

		Type = None
		TypesDeterminations = {
			"Манга": Types.manga,
			"Манхва": Types.manhwa,
			"Маньхуа": Types.manhua,
			"Рукомикс": Types.russian_comic,
			"Западный комикс": Types.western_comic,
			"Индонезийский комикс": Types.indonesian_comic
		}
		SiteType = data["type"]["name"]
		if SiteType in TypesDeterminations.keys(): Type = TypesDeterminations[SiteType]

		return Type

	def __try_get_chapter_from_exmanga(self, chapter_id: int) -> list[ImageData]:
		"""
		Пробует получить слайды главы через расширение **ExManga**.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:return: Список слайдов главы.
		:rtype: list[ImageData]
		"""
		
		if not self.source_operator.extensions.is_enabled(extensions.ExManga): return []
		Slides: list[ImageData] = self.__ExManga.get_slides_data(chapter_id)
		if not Slides: return []
		Title = cast(Manga, self.title)
		SlidesCound: int = len(Slides)

		for Index in range(SlidesCound):
			Slide: ImageData = Slides[Index]
			Result = self.__ExManga.download_slide(Title, chapter_id, Slide)
			
			if Result.error_message:
				self.portals.printer.error("Chapter slides downloading failed.")
				return []

		return Slides

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def _get_age_limit(self, data: dict) -> int:
		"""
		Определяет возрастной рейтинг.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Возрастной рейтинг.
		:rtype: int
		"""

		Ratings = {
			0: 0,
			1: 16,
			2: 18
		}
		Rating = Ratings[data["age_limit"]["id"]]

		return Rating 	

	def _get_covers(self, data: dict):
		"""
		Парсит данные обложек.

		:param data: Словарь данных тайтла.
		:type data: dict
		"""

		title = cast(Manga, self.title)
		
		covers_data: dict[str, str] = data["cover"]
		covers: list[ImageData] = []

		if self.settings.custom.only_best_cover:
			best_cover_uri = covers_data["high"]
			cover = ImageData(f"https://{self.manifest.domain}{best_cover_uri}")
			covers.append(cover)

		else:
			for cover_uri in reversed(covers_data.values()):
				cover = ImageData(f"https://{self.manifest.domain}{cover_uri}")
				covers.append(cover)


		for cover in covers:
			if cover.link.endswith("/media/None"):
				covers.remove(cover)

		title.data.set_covers(covers)

	def _get_description(self, data: dict) -> str | None:
		"""
		Получает описание тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Описание тайтла.
		:rtype: str | None
		"""

		Description = None

		if data.get("description"):
			Description = HTML(data["description"]).plain_text
			Description = Description.replace("\r", "").replace("\xa0", " ").strip()
			Description = remove_recurring_substrings(Description, "\n")
			Description = zerotify(Description)

		return Description

	def _get_genres(self, data: dict) -> list[str]:
		"""
		Получает жанры.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Список жанров.
		:rtype: list[str]
		"""

		Genres = []
		for Genre in data["genres"]: Genres.append(Genre["name"])

		return Genres

	def _get_persons(self) -> list[Person]:
		"""
		Получает список персонажей.

		:return: Список персонажей.
		:rtype: list[Person]
		"""

		Title = cast(Manga, self.title)

		Persons = []
		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{Title.data.id}/characters/?")
		
		if Response.ok and Response.json:

			for PersonData in Response.json:
				Buffer = Person(PersonData["name"])
				Buffer.add_another_name(PersonData["alt_name"])

				if PersonData["cover"]:
					Buffer.add_image(ImageData(f"https://{self.manifest.domain}/media/" + PersonData["cover"]["high"]))
					Buffer.add_image(ImageData(f"https://{self.manifest.domain}/media/" + PersonData["cover"]["mid"]))
					
				Buffer.set_description(HTML(PersonData["description"]).plain_text if PersonData["description"] else None)
				Persons.append(Buffer)

		return Persons

	def _get_status(self, data: dict) -> Statuses | None:
		"""
		Определяет статус тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Статус.
		:rtype: Statuses | None
		"""

		Status = None
		StatusesDetermination = {
			"Продолжается": Statuses.ongoing,
			"Закончен": Statuses.completed,
			"Анонс": Statuses.announced,
			"Заморожен": Statuses.dropped,
			"Нет переводчика": Statuses.dropped,
			"Не переводится (лицензировано)": Statuses.dropped
		}
		SiteStatusIndex = data["status"]["name"]
		if SiteStatusIndex in StatusesDetermination.keys(): Status = StatusesDetermination[SiteStatusIndex]

		return Status

	def _get_tags(self, data: dict) -> list[str]:
		"""
		Получает список тегов.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Cписок тегов.
		:rtype: list[str]
		"""

		Tags = []
		for Tag in data["categories"]: Tags.append(Tag["name"])

		return Tags
	
	def _get_title_data(self) -> "WebResponse":
		"""
		Запрашивает данные тайтла.
		
		Также при ошибке с кодом 404 пытается обновить алиас тайтла, если включено расширение **slugger**.

		:return: Контейнер ответа на запрос.
		:rtype: WebResponse
		"""

		Title = cast(Manga, self.title)
		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{Title.data.slug}/")

		if Response.status_code == 404 and self.source_operator.extensions.is_enabled(extensions.Slugger):

			if Title.load(Title.data.slug):
				self.portals.printer.emit("Loaded local file.")
			else:
				return Response

			if self.__Slugger.update_title_slug(Title):
				return self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{Title.data.slug}/")

		return Response
from time import sleep
from typing import cast

from dublib.functions.data import RemoveRecurringSubstrings, Zerotify
from dublib.polyglot import HTML

from melon.core.base.formats.base_format import ImageData, Person, Statuses
from melon.core.base.formats.manga import BaseBranch, Chapter, Manga, Types
from melon.core.base.parsers.base_manga_parser import BaseMangaParser

from .extensions import exmanga
from .functions import MergeLists

class Parser(BaseMangaParser):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#
	
	def _Amend(self, branch: BaseBranch, chapter: Chapter) -> str | None:
		"""
		Дополняет главу дайными о контенте.

		:param branch: Ветвь.
		:type branch: BaseBranch
		:param chapter: Глава.
		:type chapter: Chapter
		:return: Дополнительное необязательное сообщение о дополнении.
		:rtype: str | None
		"""

		Slides: list[ImageData] = self.__GetSlides(chapter)
		Message: str | None = None

		if Slides:
			FirstSlideLink: str = Slides[0].link

			if FirstSlideLink.startswith("file:") or self.__ExManga.options.domain in FirstSlideLink:
				Message = "Received from ExManga."
				
			chapter.set_slides(self.__GetSlides(chapter))

		return Message

	def _Parse(self):
		"""Получает основные данные тайтла."""

		Title = cast(Manga, self.title)

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{Title.slug}/")

		if Response.ok and Response.json:
			Data = Response.json
			
			Title.set_id(Data["id"])
			Title.set_content_language("rus")
			Title.set_localized_name(Data["main_name"])
			Title.set_eng_name(Data["secondary_name"])
			Title.set_another_names(Data["another_name"].split(" / "))
			self._GetCovers(Data)
			Title.set_publication_year(Data["issue_year"])
			Title.set_description(self._GetDescription(Data))
			Title.set_age_limit(self._GetAgeLimit(Data))
			Title.set_type(self.__GetType(Data))
			Title.set_status(self._GetStatus(Data))
			Title.set_is_licensed(Data["is_licensed"])
			Title.set_genres(self._GetGenres(Data))
			Title.set_tags(self._GetTags(Data))
			Title.set_persons(self._GetPersons())
			self.__GetBranches(Data)

		elif Response.status_code == 404: self.portals.title_not_found(Title)
		else: self.portals.request_error(Response, "Unable to request title data.")

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""
	
		self._IsPaidChaptersLocked = False

		self.__ExManga = exmanga.Extension(self.source_operator)

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ВЗАИМОДЕЙСТВИЯ С РАСШИРЕНИЯМИ <<<<< #
	#==========================================================================================#

	def __TryGetChabterFromExManga(self, chapter_id: int) -> list[ImageData]:
		"""
		Пробует получить слайды главы через расширение **ExManga**.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:return: Список слайдов главы.
		:rtype: list[ImageData]
		"""
		
		if not self.__ExManga.options.is_enabled: return []
		Slides: list[ImageData] = self.__ExManga.get_slides_data(chapter_id)
		if not Slides: return []
		Title = cast(Manga, self.title)
		SlidesCound: int = len(Slides)

		for Index in range(SlidesCound):
			Slide: ImageData = Slides[Index]
			Slide, Result = self.__ExManga.download_slide(Title, chapter_id, Slide)

			if Index + 1 != SlidesCound and not Result.is_already_exists: self.settings.common.sleep_delay()
			
			if Result.error_message:
				self.portals.printer.error("Chapter slides downloading failed.")
				return []

		return Slides

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def __GetBranches(self, data: dict):
		"""
		Получает ветви тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		"""

		Title = cast(Manga, self.title)

		for CurrentBranchData in data["branches"]:
			BranchID = CurrentBranchData["id"]
			CurrentBranch = BaseBranch(BranchID)
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

						if self.settings.custom["add_free_publication_date"] and Buffer.is_paid:
							Buffer.extra_data.set("free-publication-date", CurrentChapter["pub_date"])
						
						CurrentBranch.add_chapter(Buffer)

				else:
					self.portals.request_error(Response, "Unable to request chapter.", exception = False)

				sleep(self.settings.common.delay)

			CurrentBranch.reverse()
			Title.add_branch(CurrentBranch)	

	def __GetSlides(self, chapter: Chapter) -> list[ImageData]:
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
				Slides = self.__TryGetChabterFromExManga(chapter.id)
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

	def __GetType(self, data: dict) -> Types | None:
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

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def _GetAgeLimit(self, data: dict) -> int:
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

	def _GetCovers(self, data: dict):
		"""
		Парсит данные обложек и сверяет их с шаблонами для фильтрации заглушек.

		:param data: Словарь данных тайтла.
		:type data: dict
		"""

		Title = cast(Manga, self.title)
		Covers = []

		for CoverURI in data["cover"].values():

			if CoverURI not in ("/media/None",):
				Buffer = ImageData(f"https://{self.manifest.domain}{CoverURI}")
				Covers.append(Buffer)

		if Covers: Title.set_covers(Covers)

	def _GetDescription(self, data: dict) -> str | None:
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
			Description = RemoveRecurringSubstrings(Description, "\n")
			Description = Zerotify(Description)

		return Description

	def _GetGenres(self, data: dict) -> list[str]:
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

	def _GetPersons(self) -> list[Person]:
		"""
		Получает список персонажей.

		:return: Список персонажей.
		:rtype: list[Person]
		"""

		Title = cast(Manga, self.title)

		Persons = []
		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{Title.id}/characters/?")
		
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

	def _GetStatus(self, data: dict) -> Statuses | None:
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

	def _GetTags(self, data: dict) -> list[str]:
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
	
from Source.Core.Base.Formats.Manga import BaseBranch, Chapter, Manga, Types
from Source.Core.Base.Formats.BaseFormat import ImageData, Person, Statuses
from Source.Core.Base.Parsers.BaseMangaParser import BaseMangaParser

from dublib.Methods.Data import RemoveRecurringSubstrings, Zerotify

from dublib.Polyglot import HTML

from typing import cast
from time import sleep
import itertools

class Parser(BaseMangaParser):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#
	
	def _Amend(self, branch: BaseBranch, chapter: Chapter):
		"""
		Дополняет главу дайными о контенте.

		:param branch: Ветвь.
		:type branch: BaseBranch
		:param chapter: Глава.
		:type chapter: Chapter
		"""

		chapter.set_slides(self.__GetSlides(chapter))

	def _Parse(self):
		"""Получает основные данные тайтла."""

		self._Title = cast(Manga, self._Title)

		Response = self.requestor.get(f"https://{self.manifest.site}/api/v2/titles/{self._Title.slug}/")

		if Response.ok and Response.json:
			Data = Response.json
			
			self._Title.set_id(Data["id"])
			self._Title.set_content_language("rus")
			self._Title.set_localized_name(Data["main_name"])
			self._Title.set_eng_name(Data["secondary_name"])
			self._Title.set_another_names(Data["another_name"].split(" / "))
			self._GetCovers(Data)
			self._Title.set_publication_year(Data["issue_year"])
			self._Title.set_description(self._GetDescription(Data))
			self._Title.set_age_limit(self._GetAgeLimit(Data))
			self._Title.set_type(self.__GetType(Data))
			self._Title.set_status(self._GetStatus(Data))
			self._Title.set_is_licensed(Data["is_licensed"])
			self._Title.set_genres(self._GetGenres(Data))
			self._Title.set_tags(self._GetTags(Data))
			self._Title.set_persons(self._GetPersons())
			self.__GetBranches(Data)

		elif Response.status_code == 404:
			self.portals.title_not_found(self._Title)
		else:
			self.portals.request_error(Response, "Unable to request title data.")

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""
	
		self._IsPaidChaptersLocked = False

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __MergeListOfLists(self, list_of_lists: list) -> list:
		"""
		Раскрывает вложенные списки внутри списка контейнера.

		:param list_of_lists: Список, который может являться списком списков.
		:type list_of_lists: list
		:return: Обработанный список.
		:rtype: list
		"""
		
		if len(list_of_lists) > 0 and type(list_of_lists[0]) is list:
			return list(itertools.chain.from_iterable(list_of_lists))

		return list_of_lists

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def __GetBranches(self, data: dict):
		"""
		Получает ветви тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		"""

		self._Title = cast(Manga, self._Title)

		for CurrentBranchData in data["branches"]:
			BranchID = CurrentBranchData["id"]
			CurrentBranch = BaseBranch(BranchID)
			BranchPage = 1

			while True:
				Response = self.requestor.get(f"https://{self.manifest.site}/api/v2/titles/chapters/?branch_id={BranchID}&ordering=-index&page={BranchPage}")
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
							Buffer.add_extra_data("free-publication-date", CurrentChapter["pub_date"])
						
						CurrentBranch.add_chapter(Buffer)

				else:
					self.portals.request_error(Response, "Unable to request chapter.", exception = False)

				sleep(self.settings.common.delay)

			CurrentBranch.reverse()
			self._Title.add_branch(CurrentBranch)	

	def __GetSlides(self, chapter: Chapter) -> list[ImageData]:
		"""
		Получает данные о слайдах главы.

		:param chapter: Глава.
		:type chapter: Chapter
		:return: Список данных слайдов.
		:rtype: list[ImageData]
		"""

		Slides: list[ImageData] = list()

		if chapter.is_paid and self._IsPaidChaptersLocked:
			self.portals.chapter_skipped(chapter)
			return Slides

		Response = self.requestor.get(f"https://{self.manifest.site}/api/v2/titles/chapters/{chapter.id}/")
		
		if Response.ok and Response.json:
			Data = Response.json
			Data["pages"] = self.__MergeListOfLists(Data["pages"])

			for SlideData in Data["pages"]:
				Link = SlideData["link"]
				Width, Height = SlideData["width"], SlideData["height"]
				Buffer = ImageData(Link)
				Buffer.create_resolution(Width, Height)
				Slides.append(Buffer)

		elif Response.status_code in (401, 423):
			if chapter.is_paid: self._IsPaidChaptersLocked = True
			self.portals.chapter_skipped(chapter)

		else:
			self.portals.request_error(Response, "Unable to request chapter content.", exception = False)

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

		self._Title = cast(Manga, self._Title)
		Covers = list()

		for CoverURI in data["cover"].values():

			if CoverURI not in ("/media/None",):
				Buffer = ImageData(f"https://{self.manifest.site}{CoverURI}")
				Covers.append(Buffer)

		if Covers: self._Title.set_covers(Covers)

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

		Genres = list()
		for Genre in data["genres"]: Genres.append(Genre["name"])

		return Genres

	def _GetPersons(self) -> list[Person]:
		"""
		Получает список персонажей.

		:return: Список персонажей.
		:rtype: list[Person]
		"""

		self._Title = cast(Manga, self._Title)

		Persons = list()
		Response = self.requestor.get(f"https://{self.manifest.site}/api/v2/titles/{self._Title.id}/characters/?")
		
		if Response.ok and Response.json:

			for PersonData in Response.json:
				Buffer = Person(PersonData["name"])
				Buffer.add_another_name(PersonData["alt_name"])

				if PersonData["cover"]:
					Buffer.add_image(ImageData(f"https://{self.manifest.site}/media/" + PersonData["cover"]["high"]))
					Buffer.add_image(ImageData(f"https://{self.manifest.site}/media/" + PersonData["cover"]["mid"]))
					
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

		Tags = list()
		for Tag in data["categories"]: Tags.append(Tag["name"])

		return Tags
	
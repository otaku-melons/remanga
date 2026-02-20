from Source.Core.Base.Formats.Manga import Branch, Chapter, Types
from Source.Core.Base.Formats.BaseFormat import Person, Statuses
from Source.Core.Base.Parsers.MangaParser import MangaParser
from Source.Core.Base.Formats.Manga.Elements import Slide

from dublib.Methods.Data import RemoveRecurringSubstrings, Zerotify
from dublib.Methods.Filesystem import ListDir
from dublib.WebRequestor import WebRequestor
from dublib.Polyglot import HTML

from datetime import datetime, timedelta
from typing import Iterable
from time import sleep
import math

from skimage.metrics import structural_similarity
from skimage import io
import cv2

class Parser(MangaParser):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _InitializeRequestor(self) -> WebRequestor:
		"""Инициализирует модуль WEB-запросов."""

		WebRequestorObject = super()._InitializeRequestor()
		if self._Settings.custom["token"]: WebRequestorObject.config.add_header("Authorization", self._Settings.custom["token"])

		return WebRequestorObject
	
	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""
	
		self._IsPaidChaptersLocked = False

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __GetBranches(self, data: str):
		"""Получает ветви тайтла."""

		for CurrentBranchData in data["branches"]:
			BranchID = CurrentBranchData["id"]
			CurrentBranch = Branch(BranchID)
			BranchPage = 1

			while True:
				Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/chapters/?branch_id={BranchID}&ordering=-index&page={BranchPage}")
				BranchPage += 1
				
				if Response.status_code == 200:
					Data = Response.json["results"]
					if not Data: break

					for CurrentChapter in Data:
						Translators = [sub["name"] for sub in CurrentChapter["publishers"]]
						Name = CurrentChapter["name"] if CurrentChapter["name"] != "null" else None
						Buffer = Chapter(self._SystemObjects, self._Title)
						Buffer.set_id(CurrentChapter["id"])
						Buffer.set_volume(CurrentChapter["tome"])
						Buffer.set_number(CurrentChapter["chapter"])
						Buffer.set_name(Name)
						Buffer.set_is_paid(CurrentChapter["is_paid"])
						Buffer.set_workers(Translators)
						if self._Settings.custom["add_free_publication_date"] and Buffer.is_paid: Buffer.add_extra_data("free-publication-date", CurrentChapter["pub_date"])
						
						CurrentBranch.add_chapter(Buffer)

				else: self._Portals.request_error(Response, "Unable to request chapter.", exception = False)

				sleep(self._Settings.common.delay)

			CurrentBranch.reverse()
			self._Title.add_branch(CurrentBranch)	

	def __GetSlides(self, chapter: Chapter) -> list[Slide]:
		"""
		Получает данные о слайдах главы.
			chapter – данные главы.
		"""

		Slides = list()

		if chapter.is_paid and self._IsPaidChaptersLocked:
			self._Portals.chapter_skipped(chapter)
			return Slides

		Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/chapters/{chapter.id}/")
		
		if Response.status_code == 200:
			Data = Response.json
			Data["pages"] = self.__MergeListOfLists(Data["pages"])

			for SlideData in Data["pages"]:
				SlideObject = Slide(self._SystemObjects, chapter)
				SlideObject.set_link(SlideData["link"])
				SlideObject.set_resolution(SlideData["width"], SlideData["height"])
				IsFiltered = False
				if self._Settings.custom["ru_links"]: SlideObject.set_link(self.__RusificateLink(SlideObject.link))
				if not IsFiltered: Slides.append(SlideObject)

		elif Response.status_code in [401, 423]:
			if chapter.is_paid: self._IsPaidChaptersLocked = True
			self._Portals.chapter_skipped(chapter)

		else:
			self._Portals.request_error(Response, "Unable to request chapter content.", exception = False)

		return Slides

	def __GetType(self, data: dict) -> str:
		"""
		Получает тип тайтла.
			data – словарь данных тайтла.
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

	def __MergeListOfLists(self, list_of_lists: list) -> list:
		"""
		Объединяет список списков в один список.
			list_of_lists – список списоков.
		"""
		
		if len(list_of_lists) > 0 and type(list_of_lists[0]) is list:
			Result = list()
			for List in list_of_lists: Result.extend(List)

			return Result

		else: return list_of_lists

	def __RusificateLink(self, link: str) -> str:
		"""
		Задаёт домен российского сервера для ссылки на слайд.
			link – ссылка на слайд.
		"""

		if link.startswith("https://img5.reimg.org"): link = link.replace("https://img5.reimg.org", "https://reimg2.org")
		link = link.replace("reimg.org", "reimg2.org")

		return link

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#
	
	def _CheckForStubs(self) -> bool:
		"""Проверяет, является ли обложка заглушкой."""

		FiltersDirectories = ListDir(f"Parsers/{self._Manifest.name}/Filters")

		for FilterIndex in FiltersDirectories:
			Patterns = ListDir(f"Parsers/{self._Manifest.name}/Filters/{FilterIndex}")
			
			for Pattern in Patterns:
				Result = self._CompareImages(f"Parsers/{self._Manifest.name}/Filters/{FilterIndex}/{Pattern}")
				if Result != None and Result < 50.0: return True
		
		return False
	
	def _Collect(self, filters: str | None = None, pages: int | None = None) -> tuple[str]:
		"""
		Собирает список тайтлов по заданным параметрам.
			filters – строка из URI каталога, описывающая параметры запроса;\n
			pages – количество запрашиваемых страниц.
		"""

		Slugs = list()
		IsCollected = False
		Page = 1
		
		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/search/catalog/?page={Page}&count=30&ordering=-id&{filters}")
			
			if Response.status_code == 200:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])
				if not PageContent or pages and Page == pages: IsCollected = True
				self._Portals.collect_progress_by_page(Page)
				Page += 1
				sleep(self._Settings.common.delay)

			else:
				self._Portals.request_error(Response, "Unable to request catalog.")
				raise Exception("Unable to request catalog.")

		return tuple(Slugs)
	
	def _CollectUpdates(self, period: int, pages: int | None = None) -> tuple[str]:
		"""
		Собирает алиасы тайтлов, обновлённых за указанный период времени (в часах).

		Часы округляются до суток в большую сторону.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int
		:param pages: Количество запрашиваемых страниц.
		:type pages: int | None
		:raises Exception: Выбрасывается при невозможности запросить каталог.
		:return: Последовательность алиасов тайтлов.
		:rtype: tuple[str]
		:raises ParsingError: Выбрасывается при активации соответствующего аргумента.
		"""

		Slugs = list()
		IsCollected = False
		Page = 1
		Now = datetime.now()
		TargetDate = Now - timedelta(days = math.ceil(period / 24))
		Now = Now.strftime("%Y-%m-%d")
		TargetDate = TargetDate.strftime("%Y-%m-%d")

		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/search/catalog/?count=30&last_chapter_uploaded_gte={TargetDate}&last_chapter_uploaded_lte={Now}&ordering=-score&page={Page}")
			
			if Response.status_code == 200:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])
				if not PageContent or pages and Page == pages: IsCollected = True
				self._Portals.collect_progress_by_page(Page)
				Page += 1
				sleep(self._Settings.common.delay)

			else: self._Portals.request_error(Response, "Unable to request catalog.")

		return tuple(Slugs)

	def _CompareImages(self, pattern_path: str) -> float | None:
		"""
		Сравнивает изображение с фильтром.
			url – ссылка на обложку;\n
			pattern_path – путь к шаблону.
		"""

		Differences = None

		try:
			Temp = self._SystemObjects.temper.parser_temp
			Pattern = io.imread(f"{Temp}/cover")
			Image = cv2.imread(pattern_path)
			Pattern = cv2.cvtColor(Pattern, cv2.COLOR_BGR2GRAY)
			Image = cv2.cvtColor(Image, cv2.COLOR_BGR2GRAY)
			PatternHeight, PatternWidth = Pattern.shape
			ImageHeight, ImageWidth = Image.shape
		
			if PatternHeight == ImageHeight and PatternWidth == ImageWidth:
				(Similarity, Differences) = structural_similarity(Pattern, Image, full = True)
				Differences = 100.0 - (float(Similarity) * 100.0)

		except Exception as ExceptionData:
			self._Portals.error("Problem occurred during filtering stubs: \"" + str(ExceptionData) + "\".")		
			Differences = None

		return Differences

	def _GetAgeLimit(self, data: dict) -> int:
		"""
		Получает возрастной рейтинг.
			data – словарь данных тайтла.
		"""

		Ratings = {
			0: 0,
			1: 16,
			2: 18
		}
		Rating = Ratings[data["age_limit"]["id"]]

		return Rating 	

	def _GetCovers(self, data: dict) -> list[str]:
		"""Получает список обложек."""

		Covers = list()

		for CoverURI in data["cover"].values():

			if CoverURI not in ["/media/None"]:
				Buffer = {
					"link": f"https://{self._Manifest.site}{CoverURI}",
					"filename": CoverURI.split("/")[-1]
				}

				if self._Settings.common.sizing_images:
					Buffer["width"] = None
					Buffer["height"] = None

				Covers.append(Buffer)

				if self._Settings.custom["unstub"]:
					self._ImagesDownloader.temp_image(
						url = Buffer["link"],
						filename = "cover",
						is_full_filename = True
					)
					
					if self._CheckForStubs():
						Covers = list()
						self._Portals.covers_unstubbed()
						break

		return Covers

	def _GetDescription(self, data: dict) -> str | None:
		"""
		Получает описание.
			data – словарь данных тайтла.
		"""

		Description = None

		if data["description"]:
			Description = HTML(data["description"]).plain_text
			Description = Description.replace("\r", "").replace("\xa0", " ").strip()
			Description = RemoveRecurringSubstrings(Description, "\n")
			Description = Zerotify(Description)

		return Description

	def _GetGenres(self, data: dict) -> list[str]:
		"""
		Получает список жанров.
			data – словарь данных тайтла.
		"""

		Genres = list()
		for Genre in data["genres"]: Genres.append(Genre["name"])

		return Genres

	def _GetPersons(self) -> list[Person]:
		"""Получает список персонажей."""

		Persons = list()
		Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/{self._Title.id}/characters/?")
		
		if Response.status_code == 200:

			for PersonData in Response.json:
				Buffer = Person(PersonData["name"])
				Buffer.add_another_name(PersonData["alt_name"])

				if PersonData["cover"]:
					Buffer.add_image(f"https://{self._Manifest.site}/media/" + PersonData["cover"]["high"])
					Buffer.add_image(f"https://{self._Manifest.site}/media/" + PersonData["cover"]["mid"])
					
				Buffer.set_description(HTML(PersonData["description"]).plain_text if PersonData["description"] else None)
				Persons.append(Buffer)

		return Persons

	def _GetStatus(self, data: dict) -> str:
		"""
		Получает статус.
			data – словарь данных тайтла.
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
			data – словарь данных тайтла.
		"""

		Tags = list()
		for Tag in data["categories"]: Tags.append(Tag["name"])

		return Tags

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def amend(self, branch: Branch, chapter: Chapter):
		"""
		Дополняет главу дайными о слайдах.

		:param branch: Данные ветви.
		:type branch: Branch
		:param chapter: Данные главы.
		:type chapter: Chapter
		"""

		chapter.set_slides(self.__GetSlides(chapter))

	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> Iterable[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая фильтрацию (подробнее в README.md парсера).
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: Iterable[str]
		"""

		Slugs: tuple[str] = self._Collect(filters, pages) if not period else self._CollectUpdates(period, pages)

		return Slugs
	
	def parse(self):
		"""Получает основные данные тайтла."""

		Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/{self._Title.slug}/")

		if Response.status_code == 200:
			Data = Response.json
			
			self._Title.set_site(self._Manifest.site)
			self._Title.set_id(Data["id"])
			self._Title.set_content_language("rus")
			self._Title.set_localized_name(Data["main_name"])
			self._Title.set_eng_name(Data["secondary_name"])
			self._Title.set_another_names(Data["another_name"].split(" / "))
			self._Title.set_covers(self._GetCovers(Data))
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

		elif Response.status_code == 404: self._Portals.title_not_found(self._Title)
		else: self._Portals.request_error(Response, "Unable to request title data.")
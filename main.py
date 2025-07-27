from Source.Core.Base.Formats.Manga import Branch, Chapter, Types
from Source.Core.Base.Formats.BaseFormat import Person, Statuses
from Source.Core.Base.Parsers.MangaParser import MangaParser

from dublib.Methods.Data import RemoveRecurringSubstrings, Zerotify
from dublib.Methods.Filesystem import ListDir
from dublib.WebRequestor import WebRequestor
from dublib.Polyglot import HTML

from datetime import datetime
from time import sleep

from skimage.metrics import structural_similarity
from skimage import io
import dateparser
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
			ChaptersCount = CurrentBranchData["count_chapters"]
			CurrentBranch = Branch(BranchID)
			PagesCount = int(ChaptersCount / 50) + 1
			if ChaptersCount % 50: PagesCount += 1
			
			for BranchPage in range(1, PagesCount):
				Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/chapters/?branch_id={BranchID}&ordering=-index&page={BranchPage}")

				if Response.status_code == 200:
					Data = Response.json["results"]

					for CurrentChapter in Data:
						Translators = [sub["name"] for sub in CurrentChapter["publishers"]]
						Name = CurrentChapter["name"] if CurrentChapter["name"] != "null" else None
						Buffer = Chapter(self._SystemObjects)
						Buffer.set_id(CurrentChapter["id"])
						Buffer.set_volume(CurrentChapter["tome"])
						Buffer.set_number(CurrentChapter["chapter"])
						Buffer.set_name(Name)
						Buffer.set_is_paid(CurrentChapter["is_paid"])
						Buffer.set_workers(Translators)
						if self._Settings.custom["add_free_publication_date"] and Buffer.is_paid: Buffer.add_extra_data("free-publication-date", CurrentChapter["pub_date"])
						
						CurrentBranch.add_chapter(Buffer)

				else: self._Portals.request_error(Response, "Unable to request chapter.", exception = False)

				if BranchPage < PagesCount: sleep(self._Settings.common.delay)

			self._Title.add_branch(CurrentBranch)	

	def __GetSlides(self, chapter: Chapter) -> list[dict]:
		"""
		Получает данные о слайдах главы.
			chapter – данные главы.
		"""

		Slides = list()

		if chapter.is_paid and self._IsPaidChaptersLocked:
			self._Portals.chapter_skipped(self._Title, chapter)
			return Slides

		Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/chapters/{chapter.id}/")
		
		if Response.status_code == 200:
			Data = Response.json
			Data["pages"] = self.__MergeListOfLists(Data["pages"])

			for SlideIndex in range(len(Data["pages"])):
				Buffer = {
					"index": SlideIndex + 1,
					"link": Data["pages"][SlideIndex]["link"],
					"width": Data["pages"][SlideIndex]["width"],
					"height": Data["pages"][SlideIndex]["height"]
				}
				IsFiltered = False
				if self._Settings.custom["ru_links"]: Buffer["link"] = self.__RusificateLink(Buffer["link"])
				if not IsFiltered: Slides.append(Buffer)

		elif Response.status_code in [401, 423]:
			if chapter.is_paid: self._IsPaidChaptersLocked = True
			self._Portals.chapter_skipped(self._Title, chapter)

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
	
	def _Collect(self, filters: str | None = None, pages: int | None = None) -> list[str]:
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

		return Slugs
	
	def _CollectUpdates(self, period: int | None = None, pages: int | None = None) -> list[str]:
		"""
		Собирает список обновлений тайтлов по заданным параметрам.
			period – количество часов до текущего момента, составляющее период получения данных;\n
			pages – количество запрашиваемых страниц.
		"""

		Slugs = list()
		period *= 3600
		IsCollected = False
		Page = 1
		NowTimestamp = datetime.now().timestamp()

		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/titles/last-chapters/?page={Page}&count=30")
			
			if Response.status_code == 200:
				PageContent = Response.json["results"]

				for Note in PageContent:
					UploadTimestamp = dateparser.parse(Note["upload_date"])
					UploadTimestamp = UploadTimestamp.replace(tzinfo = None).timestamp()
					Delta = NowTimestamp - UploadTimestamp
					Delta = int(abs(Delta))
					
					if not period or Delta <= period:
						Slugs.append(Note["title"]["dir"])

					else:
						Slugs = list(set(Slugs))
						IsCollected = True
						break
					
				if not PageContent or pages and Page == pages: IsCollected = True
				self._Portals.collect_progress_by_page(Page)
				Page += 1
				sleep(self._Settings.common.delay)

			else:
				self._Portals.request_error(Response, "Unable to request catalog.")
				raise Exception("Unable to request catalog.")

		return Slugs

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
						self._Portals.covers_unstubbed(self._Title)
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
			branch – данные ветви;\n
			chapter – данные главы.
		"""

		Slides = self.__GetSlides(chapter)
		for Slide in Slides: chapter.add_slide(Slide["link"], Slide["width"], Slide["height"])

	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> list[str]:
		"""
		Собирает список тайтлов по заданным параметрам.
			period – количество часов до текущего момента, составляющее период получения данных;\n
			filters – строка, описывающая фильтрацию (подробнее в README.md);\n
			pages – количество запрашиваемых страниц каталога.
		"""

		Slugs: list[str] = self._Collect(filters, pages) if not period else self._CollectUpdates(period, pages)

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
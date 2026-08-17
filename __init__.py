import math
from datetime import datetime, timedelta
from time import sleep
from typing import Sequence

from dublib.web_requestor import WebRequestor

from melon.core.base.source_operator import BaseSourceOperator

class SourceOperator(BaseSourceOperator):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _ChekTitleByID(self, slug: str) -> bool | None:
		"""
		Проверяет существования тайтла по ID методом попытки добавления в закладки.

		:param slug: Алиас тайтла.
		:type slug: str
		:return: Возвращает статус существования файла на сервере или `None` при невозможности проверки.
		:rtype: bool | None
		"""
		
		TitleID: int | None = self.shared_data.journal.get_id_by_slug(slug)
		
		if TitleID is None:
			return None

		if not self.settings.custom.get("token"):
			self.portals.authorization_required("Checking title existing by bookmarks system requires authorization.")

		IsTitleExists: bool | None = None
		BOOKMARK_TYPE: int = 56251767 # Тип закладки: «Не интересно».
		Data: dict = {
			"title": TitleID,
			"type": BOOKMARK_TYPE
		}
		self.settings.common.sleep_delay()
		Response = self.requestor.post(f"https://{self.manifest.domain}/api/users/bookmarks/", json = Data)

		match Response.status_code:

			case 200 | 400:
				IsTitleExists = True
				self.settings.common.sleep_delay()
				self.requestor.delete(f"https://{self.manifest.domain}/api/users/bookmarks/", json = {"title_id": str(TitleID)})

			case 404:
				if Response.json:
					Message: str | None = Response.json.get("msg")
					if Message == "Тайтл не найден": IsTitleExists = False

		return IsTitleExists

	def _CollectCatalog(self, filters: str | None = None, pages: int | None = None) -> list[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param filters: Строка, описывающая параметры фильтрации.
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: list[str]
		"""

		Slugs = []
		IsCollected = False
		Page = 1
		MAX_CATALOG_PAGE = 999
		
		while not IsCollected:
			Response = self._Requestor.get(f"https://{self.manifest.domain}/api/v2/search/catalog/?page={Page}&count=30&ordering=-chapter_date&{filters}")

			if Response.status_code == 200 and Response.json:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])

				self.portals.collect_progress_by_page(Page)
				if not PageContent or pages and Page == pages: IsCollected = True
				if Page == MAX_CATALOG_PAGE:
					self.portals.printer.warning("Last catalog page reached: 999.")
					IsCollected = True
				
				Page += 1
				sleep(self._Settings.common.delay)

			else: self.portals.request_error(Response, "Unable to request catalog.")

		return Slugs
	
	def _CollectUpdates(self, period: int, pages: int | None = None) -> list[str]:
		"""
		Собирает алиасы тайтлов, обновлённых за указанный период времени (в часах).

		Часы округляются до суток в большую сторону.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int
		:param pages: Количество запрашиваемых страниц.
		:type pages: int | None
		:raises Exception: Выбрасывается при невозможности запросить каталог.
		:return: Последовательность алиасов тайтлов.
		:rtype: list[str]
		:raises ParsingError: Выбрасывается при активации соответствующего аргумента.
		"""

		Slugs = []
		IsCollected = False
		Page = 1
		MAX_CATALOG_PAGE = 999
		Now: datetime = datetime.now()
		TargetDate: datetime = Now - timedelta(days = math.ceil(period / 24))
		NowString: str = Now.strftime("%Y-%m-%d")
		TargetDateString: str = TargetDate.strftime("%Y-%m-%d")

		while not IsCollected:
			Response = self._Requestor.get(f"https://{self.manifest.domain}/api/v2/search/catalog/?count=30&last_chapter_uploaded_gte={TargetDateString}&last_chapter_uploaded_lte={NowString}&ordering=-score&page={Page}")
			
			if Response.status_code == 200 and Response.json:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])

				self.portals.collect_progress_by_page(Page)
				if not PageContent or pages and Page == pages: IsCollected = True
				if Page == MAX_CATALOG_PAGE:
					self.portals.printer.warning("Last catalog page reached: 999.")
					IsCollected = True
				
				Page += 1
				sleep(self._Settings.common.delay)

			else: self.portals.request_error(Response, "Unable to request catalog.")

		return Slugs

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _CollectSlugs(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> Sequence[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая параметры фильтрации.
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: Sequence[str]
		"""

		return self._CollectCatalog(filters, pages) if not period else self._CollectUpdates(period, pages)

	def _InitializeRequestor(self) -> WebRequestor:
		"""Инициализирует модуль WEB-запросов."""

		WebRequestorObject = super()._InitializeRequestor()

		Token: str | None = self._Settings.custom.get("token")

		if Token:
			if not Token.lower().startswith("bearer"): Token = f"Bearer {Token}"
			WebRequestorObject.config.headers.set("authorization", Token)

		return WebRequestorObject

	def _IsTitleExists(self, slug: str) -> bool | None:
		"""
		Проверяет, существует ли тайтл на сервере.

		:param slug: Алиас тайтла.
		:type slug: str
		:return: Возвращает статус существования файла на сервере или `None` при невозможности проверки.
		:rtype: bool | None
		"""

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{slug}/")
		IsCheckByBookmarks: bool = bool(self.settings.custom.get("check_by_bookmarks"))

		if Response.ok: return True
		if Response.status_code == 404:
			if IsCheckByBookmarks: return self._ChekTitleByID(slug) is True
			return False

		return None
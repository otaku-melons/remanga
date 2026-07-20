from Source.Core.Base.SourceOperator import BaseSourceOperator

from dublib.WebRequestor import WebRequestor

from datetime import datetime, timedelta
from typing import Sequence
from time import sleep
import math

class SourceOperator(BaseSourceOperator):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

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

		Slugs = list()
		IsCollected = False
		Page = 1
		
		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/search/catalog/?page={Page}&count=30&ordering=-id&{filters}")
			
			if Response.status_code == 200 and Response.json:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])
				if not PageContent or pages and Page == pages: IsCollected = True
				self.portals.collect_progress_by_page(Page)
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

		Slugs = list()
		IsCollected = False
		Page = 1
		Now: datetime = datetime.now()
		TargetDate: datetime = Now - timedelta(days = math.ceil(period / 24))
		NowString: str = Now.strftime("%Y-%m-%d")
		TargetDateString: str = TargetDate.strftime("%Y-%m-%d")

		while not IsCollected:
			Response = self._Requestor.get(f"https://{self._Manifest.site}/api/v2/search/catalog/?count=30&last_chapter_uploaded_gte={TargetDateString}&last_chapter_uploaded_lte={NowString}&ordering=-score&page={Page}")
			
			if Response.status_code == 200 and Response.json:
				PageContent = Response.json["results"]
				for Note in PageContent: Slugs.append(Note["dir"])
				if not PageContent or pages and Page == pages: IsCollected = True
				self.portals.collect_progress_by_page(Page)
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
			WebRequestorObject.config.add_header("Authorization", Token)

		return WebRequestorObject
from Source.Core.Base.SourceOperator import BaseSourceOperator

from dublib.WebRequestor import WebRequestor

from datetime import datetime, timedelta
from time import sleep
import math

class SourceOperator(BaseSourceOperator):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _Collect(self, filters: str | None = None, pages: int | None = None) -> tuple[str]:
		"""
		Собирает список тайтлов по заданным параметрам.

		:param filters: Строка из URI каталога, описывающая параметры запроса.
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц.
		:type pages: int | None
		:raises ParsingError: Выбрасывается при ошибке коллекционирования.
		:return: Набор алиасов собранных тайтлов.
		:rtype: tuple[str]
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

			else: self._Portals.request_error(Response, "Unable to request catalog.")

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

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _InitializeRequestor(self) -> WebRequestor:
		"""Инициализирует модуль WEB-запросов."""

		WebRequestorObject = super()._InitializeRequestor()
		if self._Settings.custom["token"]: WebRequestorObject.config.add_header("Authorization", self._Settings.custom["token"])

		return WebRequestorObject

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> tuple[str]:
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

		Slugs = self._Collect(filters, pages) if not period else self._CollectUpdates(period, pages)

		return Slugs
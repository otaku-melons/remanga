import math
from datetime import datetime, timedelta
from typing import Sequence, override

from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.source_operator import BaseSourceOperator

from .extensions import id_checker
from .settings import CustomSettingsModel

class SourceOperator(BaseSourceOperator[CustomSettingsModel]):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> НАСЛЕДУЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _collect_catalog(self, filters: str | None = None, pages: int | None = None) -> list[str]:
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

			else: self.portals.request_error(Response, "Unable to request catalog.")

		return Slugs
	
	def _collect_updates(self, period: int, pages: int | None = None) -> list[str]:
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

			else: self.portals.request_error(Response, "Unable to request catalog.")

		return Slugs

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	@override
	def _authorize(self):
		"""
		Выполняется после `_InitializeRequestor()` и обёрнут для отлова исключений `TokenExpired`.

		Используется для установки авторизации на основе заголовка _Authorization_.
		"""

		Token: str | None = self.settings.custom.token
		if not Token: return

		Authorizator = Bearer()
		Authorizator.set_token(Token)
		self.requestor.config.headers.authorization.set_authorization_method(Authorizator)

	@override
	def _collect_slugs(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> Sequence[str]:
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

		return self._collect_catalog(filters, pages) if not period else self._collect_updates(period, pages)

	@override
	def _export_custom_settings_model(self) -> type[CustomSettingsModel]:
		"""
		Экспортирует модель кастомных настроек парсера. Модель должна быть унаследована от `CustomSettingsModel`.

		:return: Модель кастомных настроек парсера.
		:rtype: type[CustomSettingsModel]
		"""

		return CustomSettingsModel

	@override
	def _is_title_exists(self, slug: str) -> bool | None:
		"""
		Проверяет, существует ли тайтл на сервере.

		:param slug: Алиас тайтла.
		:type slug: str
		:return: Возвращает статус существования файла на сервере или `None` при невозможности проверки.
		:rtype: bool | None
		"""

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{slug}/")
		
		if Response.ok: return True
		elif Response.status_code == 404:
			if not self.__CheckerByID.options.is_enabled: return False

			TitleID: int | None = self.shared_data.journal.get_id_by_slug(slug)
			if not TitleID: return False

			return self.__CheckerByID.is_title_exists_by_id(TitleID)

		else: self.portals.request_error(Response, "Failed to check title existing.")

		return None

	@override
	def _post_init(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__CheckerByID = id_checker.Extension(self)

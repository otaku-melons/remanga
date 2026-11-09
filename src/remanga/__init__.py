import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, override
from urllib.parse import urlparse

from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.parser.enums import ContentType
from melon.core.base.source_operator import BaseSourceOperator

from .modules.id_checker import ID_Checker
from .settings.custom import CustomSettingsModel

if TYPE_CHECKING:
	from melon.core.base.parser.components.images_downloader import (
		ImageDownloadingResult,
	)

class SourceOperator(BaseSourceOperator[CustomSettingsModel]):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> PROTECTED METHODS <<<<< #
	#==========================================================================================#

	def _collect_catalog(self, filters: str | None = None, pages: int | None = None) -> list[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param filters: Строка, описывающая параметры фильтрации.
		:type filters: str | None
		:param pages: Requested pages count.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: list[str]
		"""

		Slugs = []
		IsCollected = False
		Page = 1
		MAX_CATALOG_PAGE = 999

		while not IsCollected:
			Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/search/catalog/?count=30&ordering=-score&page={Page}&{filters}")

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
			Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/search/catalog/?count=30&last_chapter_uploaded_gte={TargetDateString}&last_chapter_uploaded_lte={NowString}&ordering=-score&page={Page}")

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
	# >>>>> OVERRIDDEN METHODS <<<<< #
	#==========================================================================================#

	@override
	def _authorize(self):
		"""
		Выполняется после `_InitializeRequestor()` и обёрнут для отлова исключений `TokenExpiredError`.

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
		Collect slugs by parameters.

		Args:
			period (int | None): Period in hours.
			filters (str | None): Filters, specified by parser.
			pages (int | None, optional): Catalog pages count.

		Returns:
			Sequence[str]: Collected slugs.
		"""

		return self._collect_catalog(filters, pages) if not period else self._collect_updates(period, pages)

	@override
	def _export_custom_settings_model(self) -> type[CustomSettingsModel]:
		"""
		Export custom parser settings [pydantic](https://github.com/pydantic/pydantic) model.

		Returns:
			type[CustomSettingsModel]: Custom parser settings model.
		"""

		return CustomSettingsModel

	@override
	def _get_content_type_by_slug(self, slug: str) -> ContentType:
		"""
		Get content type by title slug.

		Args:
			slug (str): Title slug.

		Returns:
			ContentType: Content type.
		"""

		return ContentType.Manga

	@override
	def _is_title_exists(self, slug: str) -> bool | None:
		"""
		Check is title exists.

		Args:
			slug (str): Title slug.

		Returns:
			bool | None: Title existing status or `None` if unable check.
		"""

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{slug}/")

		if Response.ok:
			return True
		elif Response.status_code == 404:
			if not self.extensions_manager.is_available("remanga_idchecker"): return False

			TitleID: int | None = self.shared_data.journal.get_id_by_slug(slug)
			if not TitleID: return False

			return self.__id_checker.is_title_exists_by_id(TitleID)

		else:
			self.portals.request_error(Response, "Failed to check title existing.")

		return

	@override
	def _post_init(self):
		"""Execute after instance initialization."""

		self.__id_checker: ID_Checker = ID_Checker(self)

		# Доступ к этим доменам, вероятно, возможен только с территории стран СНГ.
		# Также эти домены не требуют авторизации.
		self.__russian_domains: tuple[str, ...] = (
			"img3.reimg2.org",
		)

	@override
	def _temp_image(self, url: str, force_mode: bool = False) -> "ImageDownloadingResult":
		"""
		Download image into parser temporary directory.

		Args:
			url (str): Image URL.
			force_mode (bool): Condition: is image overwriting enabled.

		Returns:
			ImageDownloadingResult: Image downloading result.
		"""

		if urlparse(url).netloc in self.__russian_domains:
			self.images_downloader.requestor.config.headers.authorization.disable()

		try:
			return self.images_downloader.temp_image(url, force_mode = force_mode)

		finally:
			self.images_downloader.requestor.config.headers.authorization.enable()

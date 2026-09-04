from typing import TYPE_CHECKING, override
from urllib.parse import urlparse

import orjson

from dublib.exceptions.web_requestor import TokenExpired
from dublib.web_requestor import WebConfig, WebLibs, WebRequestor
from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.extensions import BaseExtension
from melon.core.base.formats.base_format.enums import ImagesTypes
from melon.core.base.formats.manga.controller import Manga
from melon.core.base.parsers.components.images_downloader import (
	ImageDownloadingResult,
	ImagesDownloader,
)
from melon.core.base.structs.image import ImageData

from ... import functions
from .options import Options

if TYPE_CHECKING:
	from melon.core.system_objects.printer.templates.images import (
		ImageDownloadingFuture,
	)

	from ... import SourceOperator as SourceOperator
	from ...settings import CustomSettingsModel as CustomSettingsModel

class ExManga(BaseExtension["SourceOperator", "CustomSettingsModel", Options]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def images_downloader(self) -> ImagesDownloader:
		"""Оператор загрузки изображений."""

		return self.__ImagesDownloader

	@property
	def requestor(self) -> WebRequestor:
		"""Оператор запросов."""

		return self.__Requestor

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __GenerateCookies(self, token: str) -> str:
		"""
		Генерирует строку _Cookie_ для запросов.

		:param token: Токен авторизации.
		:type token: str
		:return: Строка _Cookie_.
		:rtype: str
		"""

		Cookies: dict[str, str | dict[str, bool | str]] = {
			"token": token,
			"settings": {
				"action": "read",
				"autolike": False,
				"bookmark": "0",
				"builtin": False,
				"domain": f"https://{self.source_operator.manifest.domain}",
				"mirror": f"https://{self.options.domain}",
				"noread": False,
				"noview": True,
				"preview": True,
				"sidebar": True,
				"theme": "dark",
				"toolbar": True
			}
		}

		CookiesStrings: list[str] = []

		for Key, Value in Cookies.items():
			StringValue: str = Value if type(Value) is str else orjson.dumps(Value).decode()
			CookiesStrings.append(f"{Key}={StringValue}")

		return "; ".join(CookiesStrings)

	def __InitializeRequestor(self) -> WebRequestor:
		"""
		Инициализирует модуль WEB-запросов.

		:return: Оператор запросов.
		:rtype: WebRequestor
		"""

		Config = WebConfig()
		Config.select_lib(WebLibs.requests)
		Config.set_retries_count(self.source_operator.settings.network.retries)
		Config.headers.generate_user_agent(("desktop",))
		Config.headers.automatically_accept_client_hints(True)
		Config.enable_proxy_protocol_switching(True)
		WebRequestorObject = WebRequestor(Config)
		WebRequestorObject.add_proxies(self.source_operator.settings.network.proxies)

		Token: str | None = self.options.token
		
		if Token:
			Config.headers.add("cookie", self.__GenerateCookies(Token))
			Authorizator = Bearer()

			try: Authorizator.set_jwt(Token)
			except TokenExpired: self.portals.authorization_required("ExManga token expired.")

			Config.headers.authorization.set_authorization_method(Authorizator)

		else: self.portals.authorization_required("ExManga extension requires authorization.")
		
		return WebRequestorObject

	def __IsExMangaStub(self, link: str) -> bool:
		"""
		Проверяет, ведёт ли ссылка на слайд-рекламу **ExManga**.

		:param link: Проверяемая ссылка.
		:type link: str
		:return: Возвращает `True`, если ссылка ведёт на слайд-рекламу.
		:rtype: bool
		"""

		URI: str = urlparse(link).path

		return URI.startswith("/storage/_/exmanga")

	def __ProcessImageData(self, data: dict) -> ImageData | None:
		"""
		Обрабатывает данные изображения, формирую из них структуру, фильтруя рекламу.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Структура данных изображения или `None` при фильтрации рекламы.
		:rtype: ImageData | None
		"""

		Link: str = data["link"]
		Width: int | None = data.get("width")
		Height: int | None = data.get("height")

		if self.__IsExMangaStub(Link):
			return None

		Buffer = ImageData(Link)
		Buffer.create_resolution(Width, Height)

		return Buffer

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	@override
	def _export_options_model(self) -> type[Options]:
		"""
		Возвращает модель опций.

		:return: Модель опций.
		:rtype: type[Options]
		"""

		return Options

	@override
	def _post_init(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__Requestor: WebRequestor = self.__InitializeRequestor()
		self.__ImagesDownloader: ImagesDownloader = ImagesDownloader(self._source_operator)

		self.__ImagesDownloader.set_requestor(self.__Requestor)

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def download_slide(self, title: "Manga", chapter_id: int, slide: ImageData, force_mode: bool = False) -> ImageDownloadingResult:
		"""
		Скачивает слайд в каталог изображений главы тайтла.

		:param title: Тайтл.
		:type title: Manga
		:param chapter_id: ID главы.
		:type chapter_id: int
		:param slide: Данные изображения. В случае успешного скачивания ссылка заменяется на URI локального файла.
		:type slide: ImageData
		:param force_mode: Переключает режим перезаписи существующих изображений.
		:type force_mode: bool
		:return: Результат скачивания слайда.
		:rtype: ImageDownloadingResult
		"""

		ImagesDirectory = self.source_operator.settings.directories.images

		TitleImagesDirectory = ImagesDirectory / title.used_filename
		TitleImagesDirectory.mkdir(exist_ok = True)

		SlidesDirectory = TitleImagesDirectory / "slides"
		SlidesDirectory.mkdir(exist_ok = True)

		ChapterSlidesDirectory = SlidesDirectory / str(chapter_id)
		ChapterSlidesDirectory.mkdir(exist_ok = True)
		
		Future: ImageDownloadingFuture | None = None
		if self.system_objects.options.DEBUG:
			Future = self.portals.printer.templates.images.start_downloading(slide.filename, ImagesTypes.Slide)

		self.requestor.config.headers.authorization.disable()

		Result = self.__ImagesDownloader.download_image(
			url = slide.link,
			directory = ChapterSlidesDirectory,
			force_mode = force_mode
		)
		
		if Future: Future.result(Result)
		if Result.path: slide.set_link(Result.path.resolve().as_uri())
		if not slide.resolution: slide.set_resolution(Result.resolution)

		return Result

	def get_slides_data(self, chapter_id: int) -> list[ImageData]:
		"""
		Пытается получить данные слайдов главы. В случае успеха скачивает их в каталог слайдов главы.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:return: Список данных слайдов (пуста при невозможности получения).
		:rtype: list[ImageData]
		"""

		self.requestor.config.headers.authorization.enable()
		Response = self.requestor.get(f"https://{self.options.domain}/api/chapter?id={chapter_id}")
		Slides: list[ImageData] = []
		
		if Response.ok and Response.json:
			Data: list = Response.json["data"]
			SlidesData: list[dict] = functions.MergeLists(Data)

			for SlideData in SlidesData:
				Buffer: ImageData | None = self.__ProcessImageData(SlideData)
				if Buffer: Slides.append(Buffer)

		elif Response.status_code == 404:
			self.portals.printer.emit(f"Chapter {chapter_id}. Slides not found on ExManga server.")
			return []

		else: self.portals.request_error(Response, "Unable check slides on ExManga server.")

		return Slides

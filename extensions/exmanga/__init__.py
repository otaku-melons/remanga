from urllib.parse import urlparse

import orjson

from dublib.web_requestor import WebConfig, WebLibs, WebRequestor

from melon.core.base.extensions import BaseExtension
from melon.core.base.formats.base_format import BaseTitle, ImageData
from melon.core.base.parsers.components.images_downloader import (
	ImageDownloadingResult,
	ImagesDownloader,
)

from ... import functions
from .options import Options

class Extension(BaseExtension[Options]):
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
		Config.set_retries_count(self.source_operator.settings.common.retries)
		Config.headers.generate_user_agent(("desktop",))
		Config.headers.automatically_accept_client_hints(True)
		Config.enable_proxy_protocol_switching(True)
		WebRequestorObject = WebRequestor(Config)
		WebRequestorObject.add_proxies(self.source_operator.settings.proxies)

		Token: str | None = self.options.token
		if Token: Config.headers.add("cookie", self.__GenerateCookies(Token))
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

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__Requestor: WebRequestor = self.__InitializeRequestor()
		self.__ImagesDownloader: ImagesDownloader = ImagesDownloader(self._SourceOperator)

		self.__ImagesDownloader.set_requestor(self.__Requestor)

	def _ReturnOptionsType(self) -> type[Options]:
		"""
		Возвращает тип контейнера опций.

		:return: Тип контейнера опций.
		:rtype: type[T]
		"""

		return Options

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def download_slide(self, title: "BaseTitle", chapter_id: int, slide: ImageData, force_mode: bool = False) -> tuple[ImageData, ImageDownloadingResult]:
		"""
		Скачивает слайд в каталог изображений главы тайтла.

		:param title: Тайтл.
		:type title: BaseTitle
		:param chapter_id: ID главы.
		:type chapter_id: int
		:param slide: Данные изображения. В случае успешного скачивания ссылка заменяется на URI локального файла.
		:type slide: ImageData
		:param force_mode: Переключает режим перезаписи существующих изображений.
		:type force_mode: bool
		:return: Кортеж из данных изображения и результата скачивания слайда.
		:rtype: tuple[ImageData, ImageDownloadingResult]
		"""

		ImagesDirectory = self.source_operator.settings.directories.images

		TitleImagesDirectory = ImagesDirectory / title.used_filename
		TitleImagesDirectory.mkdir(exist_ok = True)

		SlidesDirectory = TitleImagesDirectory / "slides"
		SlidesDirectory.mkdir(exist_ok = True)

		ChapterSlidesDirectory = SlidesDirectory / str(chapter_id)
		ChapterSlidesDirectory.mkdir(exist_ok = True)
		
		self.portals.printer.emit(f"Chapter {chapter_id}. Downloading \"{slide.filename}\"… ", end_line = False)

		Result = self.__ImagesDownloader.download_image(
			url = slide.link,
			directory = ChapterSlidesDirectory,
			force_mode = force_mode
		)
		
		self.portals.printer.templates.image_downloading_result(Result, show_path = False)

		if Result.path: slide.set_link(Result.path.resolve().as_uri())
		if not slide.resolution: slide.set_resolution(Result.resolution)

		return (slide, Result)

	def get_slides_data(self, chapter_id: int) -> list[ImageData]:
		"""
		Пытается получить данные слайдов главы. В случае успеха скачивает их в каталог слайдов главы.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:return: Список данных слайдов (пуста при невозможности получения).
		:rtype: list[ImageData]
		"""

		Headers: dict[str, str] = {"authorization": f"Bearer {self.options.token}"}
		Response = self.requestor.get(f"https://{self.options.domain}/api/chapter?id={chapter_id}", headers = Headers)
		Slides: list[ImageData] = []
		
		if Response.ok and Response.json:
			Data: list = Response.json["data"]
			SlidesData: list[dict] = functions.MergeLists(Data)

			for SlideData in SlidesData:
				Buffer: ImageData | None = self.__ProcessImageData(SlideData)
				if Buffer: Slides.append(Buffer)

		elif Response.status_code == 404:
			self.portals.printer.emit("Slides not found on ExManga server.")
			return []

		else: self.portals.request_error(Response, "Unable check slides on ExManga server.")

		return Slides

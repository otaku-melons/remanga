from typing import TYPE_CHECKING, override
from urllib.parse import urlparse

import orjson

from dublib.functions.filesystem import text
from dublib.web_requestor import WebConfig, WebLibs, WebRequestor
from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.extensions import BaseExtension
from melon.core.base.formats.base_format.enums import ImagesTypes
from melon.core.base.parsers.components.images_downloader import (
	ImageDownloadingResult,
	ImagesDownloader,
)
from melon.core.base.structs.image import ImageData

from ...src import functions
from .options import Options

if TYPE_CHECKING:
	from melon.core.base.formats.manga.controller import Manga
	from melon.core.system_objects.printer.templates.images import (
		ImageDownloadingFuture,
	)

	from ... import SourceOperator as SourceOperator

class Extension(BaseExtension["SourceOperator", Options]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def domain(self) -> str:
		"""Домен расширения."""

		return self.__domain

	@property
	def images_downloader(self) -> ImagesDownloader:
		"""Оператор загрузки изображений."""

		return self.__images_downloader

	@property
	def requestor(self) -> WebRequestor:
		"""Оператор запросов."""

		return self.__requestor

	@property
	def token(self) -> str:
		"""Токен авторизации."""

		authorization_method = self.__requestor.config.headers.authorization.method

		if not authorization_method or not authorization_method.value:
			self.portals.authorization_required("Authorization method missing.")

		return authorization_method.value

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ АВТОРИЗАЦИИ <<<<< #
	#==========================================================================================#

	def __authorizate(self):
		"""Выполняет процедуры авторизации."""

		token: str | None = self.__read_token()
		is_token_readed: bool = bool(token)

		if not token:
			token = self.__get_token()

		self.__set_token(token, save = not is_token_readed)

	def __get_token(self) -> str:
		"""
		Выполняет авторизацию по электронной почте и паролю.

		:return: Токен авторизации.
		:rtype: str
		"""

		body: dict[str, str] = {
			"email": self.options.email,
			"password": self.options.password
		}

		response = self.__requestor.post(f"https://{self.__domain}/api/auth/login", json = body)

		if not response.ok or not response.json:
			self.portals.request_error(response, "Authorization failed.")

		self.portals.printer.debug("Requested new token. Expires in 7 days.")

		return response.json["data"]

	def __generate_cookie(self, token: str) -> str:
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
				"mirror": f"https://{self.__domain}",
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

	def __read_token(self) -> str | None:
		"""
		Читает токен из временной директории расширения.

		:return: Токен авторизации или `None` если последний не сохранён или устарел.
		:rtype: str | None
		"""

		if not self.__token_file.exists():
			return None

		token: str = text.read(self.__token_file, split = False, strip_level = 1)
		
		if Bearer().is_jwt_expired(token):
			return None

		return token

	def __set_token(self, token: str, save: bool = True):
		"""
		Устанавливает токен авторизации.

		:param token: Токен авторизации.
		:type token: str
		:param save: Указывает, нужно ли сохранять токен.
		:type save: bool
		"""
		
		authorizator = Bearer()
		authorizator.set_jwt(token)

		self.__requestor.config.headers.set("cookie", self.__generate_cookie(token))
		self.__requestor.config.headers.authorization.set_authorization_method(authorizator)

		if save: text.write(self.__token_file, self.token)

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __initialize_requestor(self) -> WebRequestor:
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

		# При авторизации возвращается код 201.
		Config.set_good_codes((200, 201))
		
		return WebRequestorObject

	def __is_exmanga_stub(self, link: str) -> bool:
		"""
		Проверяет, ведёт ли ссылка на слайд-рекламу **ExManga**.

		:param link: Проверяемая ссылка.
		:type link: str
		:return: Возвращает `True`, если ссылка ведёт на слайд-рекламу.
		:rtype: bool
		"""

		URI: str = urlparse(link).path

		return URI.startswith("/storage/_/exmanga")

	def __process_image_data(self, data: dict) -> ImageData | None:
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

		if self.__is_exmanga_stub(Link):
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

		self.__requestor: WebRequestor = self.__initialize_requestor()
		self.__images_downloader: ImagesDownloader = ImagesDownloader(self._source_operator)
		self.__images_downloader.set_requestor(self.__requestor)

		self.__token_file = self.temp_directory / ".token"
		self.__domain: str = "mirror.exmanga.org" if self.options.use_mirror else "exmanga.org"

		self.__authorizate()

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

		Result = self.__images_downloader.download_image(
			url = slide.link,
			directory = ChapterSlidesDirectory,
			force_mode = force_mode
		)
		
		if Future: Future.result(Result)
		if Result.path: slide.set_link(Result.path.resolve().as_uri())
		if not slide.resolution: slide.set_resolution(Result.resolution)

		return Result

	def get_slides_data(self, chapter_id: int, is_token_refershed: bool = False) -> list[ImageData]:
		"""
		Пытается получить данные слайдов главы. В случае успеха скачивает их в каталог слайдов главы.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:param is_token_refershed: Указывает, обновлён ли токен перед выполнением метода. Позволяет избежать бесконечной рекурсии при невозможности авторизации.
		:type is_token_refershed: bool
		:return: Список данных слайдов (пуста при невозможности получения).
		:rtype: list[ImageData]
		"""

		self.requestor.config.headers.authorization.enable()

		params: dict[str, int] = {"id": chapter_id}
		response = self.requestor.get(f"https://{self.__domain}/api/chapter", params = params)
		
		if response.status_code == 404:
			self.portals.printer.emit(f"Chapter {chapter_id}. Slides not found on ExManga server.")
			return []

		elif response.status_code == 401:

			if not is_token_refershed:
				token: str = self.__get_token()
				self.__set_token(token)
				return self.get_slides_data(chapter_id, is_token_refershed = True)

			else:
				self.portals.authorization_required("Unable authorizate with refreshed token.")

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable check slides on ExManga server.")

		slides: list[ImageData] = []
		data: list = response.json["data"]
		slides_data: list[dict] = functions.MergeLists(data)

		for slide_data in slides_data:
			buffer: ImageData | None = self.__process_image_data(slide_data)
			if buffer: slides.append(buffer)

		return slides

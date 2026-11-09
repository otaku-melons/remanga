from typing import TYPE_CHECKING
from urllib.parse import urlparse

import orjson

from dublib.functions.filesystem import text
from dublib.web_requestor import WebConfig, WebLib, WebRequestor
from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.parser.components.images_downloader import (
	ImageDownloadingResult,
	ImagesDownloader,
)
from melon.core.base.structs.image import ImageData, ImageType

from . import functions
from .base import BaseModule

if TYPE_CHECKING:
	from pathlib import Path

	from melon.core.base.formats.manga.controller import Manga
	from melon.core.system_objects.printer.templates.images import (
		ImageDownloadingFuture,
	)

	from .. import SourceOperator as SourceOperator

class ExManga(BaseModule):
	"""ExManga slides receiver."""

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
			Future = self.portals.printer.templates.images.start_downloading(slide.filename, ImageType.Slide)

		self.requestor.config.headers.authorization.disable()

		Result = self.__images_downloader.download_image_from_data(
			data = slide,
			title = title,
			force_mode = force_mode,
		)

		if Future:
			Future.result(Result)

		return Result

	def get_slides_data(self, chapter_id: int, is_token_refreshed: bool = False) -> list[ImageData]:
		"""
		Пытается получить данные слайдов главы. В случае успеха скачивает их в каталог слайдов главы.

		:param chapter_id: ID главы.
		:type chapter_id: int
		:param is_token_refreshed: Указывает, обновлён ли токен перед выполнением метода. Позволяет избежать бесконечной рекурсии при невозможности авторизации.
		:type is_token_refreshed: bool
		:return: Список данных слайдов (пуста при невозможности получения).
		:rtype: list[ImageData]
		"""

		self.requestor.config.headers.authorization.enable()

		params: dict[str, int] = {"id": chapter_id}
		response = self.requestor.get(f"https://{self.domain}/api/chapter", params = params)

		if response.status_code == 404:
			self.portals.printer.emit(f"Chapter {chapter_id}. Slides not found on ExManga server.")
			return []

		elif response.status_code == 401:

			if not is_token_refreshed:
				token: str = self.__get_token()
				self.__set_token(token)
				return self.get_slides_data(chapter_id, is_token_refreshed = True)

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

	@property
	def domain(self) -> str:
		"""ExManga used domain."""

		return self.source_operator.settings.custom.exmanga.domain

	@property
	def images_downloader(self) -> ImagesDownloader:
		"""Images downloading operator."""

		return self.__images_downloader

	@property
	def requestor(self) -> WebRequestor:
		"""Requests operator."""

		return self.__requestor

	def _post_init(self):
		"""Execute after instance initialization."""

		self.__requestor: WebRequestor = self.__initialize_requestor()
		self.__images_downloader: ImagesDownloader = ImagesDownloader(self.source_operator)
		self.__images_downloader.set_requestor(self.__requestor)

		self.__token_file: Path = self.source_operator.temp_directory / ".exmanga_token"

		self.__authorizate()

	@property
	def token(self) -> str:
		"""Authorization token."""

		authorization_method = self.requestor.config.headers.authorization.method

		if not authorization_method or not authorization_method.value:
			self.portals.authorization_required("Authorization method missing.")

		return authorization_method.value

	def __authorizate(self):
		"""Authorizate ExManga account and get token."""

		token: str | None = self.__read_token()
		is_token_read: bool = bool(token)

		if not token:
			token = self.__get_token()

		self.__set_token(token, save = not is_token_read)

	def __get_token(self) -> str:
		"""
		Get ExManga token.

		Returns:
			str: Token.
		"""

		email: str | None = self.source_operator.settings.custom.exmanga.email
		password: str | None = self.source_operator.settings.custom.exmanga.password

		if not email or not password:
			self.portals.authorization_required("ExManga required authorization.")

		body: dict[str, str] = {
			"email": email,
			"password": password,
		}

		response = self.__requestor.post(f"https://{self.domain}/api/auth/login", json = body)

		if not response.ok or not response.json:
			self.portals.request_error(response, "Authorization failed.")

		self.portals.printer.debug("Requested new token. Expires in 7 days.")

		return response.json["data"]

	def __generate_cookie(self, token: str) -> str:
		"""
		Generate _Cookie_ header string.

		Args:
			token (str): Token.

		Returns:
			str: _Cookie_ header string.
		"""

		Cookies: dict[str, str | dict[str, bool | str]] = {
			"token": token,
			"settings": {
				"action": "read",
				"autolike": False,
				"bookmark": "0",
				"builtin": False,
				"domain": f"https://{self.source_operator.manifest.domain}",
				"mirror": f"https://{self.domain}",
				"noread": False,
				"noview": True,
				"preview": True,
				"sidebar": True,
				"theme": "dark",
				"toolbar": True,
			},
		}

		CookiesStrings: list[str] = []

		for Key, Value in Cookies.items():
			StringValue: str = Value if type(Value) is str else orjson.dumps(Value).decode()
			CookiesStrings.append(f"{Key}={StringValue}")

		return "; ".join(CookiesStrings)

	def __initialize_requestor(self) -> WebRequestor:
		"""
		Initialize requests operator.

		Returns:
			WebRequestor: Requests operator.
		"""

		Config = WebConfig()
		Config.select_lib(WebLib.requests)
		Config.set_retries_count(self.source_operator.settings.network.retries)
		Config.headers.generate_user_agent(("desktop",))
		Config.headers.automatically_accept_client_hints(True)
		Config.enable_proxy_protocol_switching(True)
		WebRequestorObject = WebRequestor(Config)
		WebRequestorObject.add_proxies(self.source_operator.settings.network.proxies)

		# If authorized 201 returns.
		Config.set_good_codes((200, 201))

		return WebRequestorObject

	def __is_exmanga_stub(self, link: str) -> bool:
		"""
		Check is link to ExManga adversitement image.

		Args:
			link (str): Image link.

		Returns:
			bool: `True` if ExManga adversitement.
		"""

		return urlparse(link).path.startswith("/storage/_/exmanga")

	def __read_token(self) -> str | None:
		"""
		Read token from file.

		Returns:
			str | None: Token.
		"""

		if not self.__token_file.exists():
			return None

		token: str = text.read(self.__token_file, split = False, strip_level = 1)

		if Bearer().is_jwt_expired(token):
			return None

		return token

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

		Buffer = ImageData(Link, ImageType.Slide)
		Buffer.create_resolution(Width, Height)

		return Buffer

	def __set_token(self, token: str, save: bool = True):
		"""
		Set authorization token.

		Args:
			token (str): Token.
			save (bool): Condition: save token in file.
		"""

		authorizator = Bearer()
		authorizator.set_jwt(token)

		self.__requestor.config.headers.set("cookie", self.__generate_cookie(token))
		self.__requestor.config.headers.authorization.set_authorization_method(authorizator)

		if save: text.write(self.__token_file, self.token)

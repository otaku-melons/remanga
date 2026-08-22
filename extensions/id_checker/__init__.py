from typing import TYPE_CHECKING, Literal

from melon.core.base.extensions import BaseExtension, BaseExtensionOptions

from .enums import BookmarkCreatioinResults

if TYPE_CHECKING:
	from dublib.web_requestor import WebRequestor, WebResponse

class Extension(BaseExtension[BaseExtensionOptions]):
	"""Расширение."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def requestor(self) -> "WebRequestor":
		"""Менеджер запросов."""

		return self.source_operator.requestor

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __GetMessageFromResponse(self, response: "WebResponse") -> str | None:
		"""
		Пытается получить сообщение из ключа _msg_ ответа на запрос.

		:param response: Ответ на запрос.
		:type response: WebResponse
		:return: Сообщение или `None` при его отсутствии.
		:rtype: str | None
		"""

		Data: dict | None = response.json
		if not Data: return None

		return Data.get("msg")

	def __CheckAuthorization(self):
		"""Проверяет наличие токена для доступа к системе закладок."""

		if not self.source_operator.settings.custom.get("token"):
			self.portals.authorization_required("Checking title existing by bookmarks system requires authorization.")

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""
		
		self.USED_BOOKMARKS_GROUP: Literal["Melon"] = "Melon"

	def _ReturnOptionsType(self) -> type[BaseExtensionOptions]:
		"""
		Возвращает тип контейнера опций.

		:return: Тип контейнера опций.
		:rtype: type[T]
		"""

		return BaseExtensionOptions

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def add_bookmark(self, title_id: int, group_id: int) -> BookmarkCreatioinResults:
		"""
		Добавляет тайтл в закладки.

		:param title_id: ID тайтла.
		:type title_id: int
		:param group_id: ID группы закладок.
		:type group_id: int
		:return: Результаты добавления закладки.
		:rtype: BookmarkCreatioinResults
		"""

		Data: dict = {
			"title": title_id,
			"type": group_id
		}
		Response = self.requestor.post(f"https://{self.manifest.domain}/api/users/bookmarks/", json = Data)
		Message: str | None = self.__GetMessageFromResponse(Response)

		for ResponseType in BookmarkCreatioinResults:
			if ResponseType.value == Message:
				return ResponseType

		return BookmarkCreatioinResults.OK

	def create_bookmarks_group(self, user_id: int, name: str | None = None) -> int:
		"""
		Создаёт Группу закладок.

		:param user_id: ID пользователя.
		:type user_id: int
		:param name: Название группы. По умолчанию берётся из атрибута `USED_BOOKMARKS_GROUP`.
		:type name: str
		:return: ID группы закладок.
		:rtype: int
		"""

		Data: dict = {
			"name": name or self.USED_BOOKMARKS_GROUP,
			"is_notify": "0",
			"is_visible": "hide"
		}
		Response = self.requestor.post(f"https://{self.manifest.domain}/api/v2/users/{user_id}/user_bookmarks/", json = Data)

		if Response.ok and Response.json:
			self.portals.printer.debug(f"Created bookmarks group: \"{self.USED_BOOKMARKS_GROUP}\".")
			Results: list[dict] = Response.json["results"]
			return Results[-1]["id"]

		else: self.portals.request_error(Response, "Failed to create bookmark type.")

	def get_bookmarks_groups(self, user_id: int) -> dict[int, str]:
		"""
		Получает группы закладок пользователя.

		:param user_id: ID пользователя.
		:type user_id: int
		:return: Словарь, в котором ключ – ID группы закладок, а значение – название группы.
		:rtype: dict[int, str]
		"""

		self.__CheckAuthorization()
		Bookmarks: dict[int, str] = {}
		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/users/{user_id}/user_bookmarks/")

		if Response.ok and Response.json:
			Results: list[dict] = Response.json["results"]
			
			for Result in Results:
				GroupID: int = Result["id"]
				GroupName: str = Result["name"]
				Bookmarks[GroupID] = GroupName

			return Bookmarks

		else: self.portals.request_error(Response, "Failed to get bookmarks group.")

	def get_current_user_id(self) -> int:
		"""
		Получает ID текущего пользователя.

		:return: ID текущего пользователя.
		:rtype: int
		"""

		self.__CheckAuthorization()

		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/users/current/")

		if Response.ok and Response.json:
			UserID: int = Response.json["id"]
			return UserID

		else: self.portals.request_error(Response, "Failed to get current user ID.")

	def get_used_bookmark_group_id(self, user_id: int) -> int:
		"""
		Получает ID используемой для проверок группы закладок.

		:param user_id: ID пользователя.
		:type user_id: int
		:return: ID используемой для проверок группы закладок.
		:rtype: int
		"""

		Bookmarks: dict[int, str] = self.get_bookmarks_groups(user_id)
		
		for ID, Name in Bookmarks.items():
			if Name == self.USED_BOOKMARKS_GROUP:
				return ID

		return self.create_bookmarks_group(user_id)

	def is_title_exists_by_id(self, title_id: int) -> bool | None:
		"""
		Проверяет существования тайтла по ID методом попытки добавления его в закладки.

		:param title_id: ID тайтла.
		:type title_id: int
		:return: Возвращает статус существования файла на сервере или `None` при невозможности проверки.
		:rtype: bool | None
		"""

		self.__CheckAuthorization()

		UserID: int = self.get_current_user_id()
		UsedGroupID: int = self.get_used_bookmark_group_id(UserID)
		AddingResult: BookmarkCreatioinResults = self.add_bookmark(title_id, UsedGroupID)

		IsTitleExists: bool | None = None

		match AddingResult:

			case BookmarkCreatioinResults.OK:
				if self.is_title_in_bookmarks_group(UserID, UsedGroupID, title_id):
					IsTitleExists = True
				else:
					IsTitleExists = False
					self.portals.printer.emit(f"Title {title_id} hidden. Marked as not found.")

				self.remove_bookmark(title_id)

			case BookmarkCreatioinResults.TITLE_ALREADY_IN_GROUP:
				IsTitleExists = True
				self.remove_bookmark(title_id)

			case BookmarkCreatioinResults.DENY:
				self.portals.printer.warning("Bookmark creation denied. Checking skipped.")

		return IsTitleExists

	def is_title_in_bookmarks_group(self, user_id: int, group_id: int, title_id: int) -> bool:
		"""
		Проверяет, находится ли тайтл на первой странице группы закладок (сортируются по дате добавления).

		:param user_id: ID пользователя.
		:type user_id: int
		:param group_id: ID группы.
		:type group_id: int
		:param title_id: ID тайтла
		:type title_id: int
		:return: Возвращает `True`, если тайтл присутствует на первой странице группы закладок.
		:rtype: bool
		"""
		Params: dict = {
			"type": group_id,
			"ordering":"-date",
			"page": 1
		}
		Response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/users/{user_id}/bookmarks/", params = Params)

		if Response.ok and Response.json:
			Results: list[dict] = Response.json["results"]

			for Result in Results:
				if Result["id"] == title_id:
					return True

		else: self.portals.request_error(Response, "Failed to get bookmarks group.")

		return False

	def remove_bookmark(self, title_id: int):
		"""
		Удаляет тайтл из закладок.

		:param title_id: ID тайтла.
		:type title_id: int
		"""

		Response = self.requestor.delete(f"https://{self.manifest.domain}/api/users/bookmarks/", json = {"title": str(title_id)})

		if Response.status_code != 204:
			self.portals.request_error(Response, "Failed to remove bookmark.")
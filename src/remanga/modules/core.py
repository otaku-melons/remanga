from typing import TYPE_CHECKING, Literal

from bs4 import BeautifulSoup

from melon.core.base.formats.base_format.branch import Branch
from melon.core.base.formats.base_format.enums import Status
from melon.core.base.formats.base_format.person import Person
from melon.core.base.structs.image import ImageData, ImageType
from melon.sdk.html_parser import HyperTextParser

from .slugger import Slugger

if TYPE_CHECKING:
	from collections.abc import Callable

	from dublib.web_requestor import WebRequestor, WebResponse

	from melon.core.base.formats.base_format.chapter import BaseChapter
	from melon.core.base.formats.base_format.controller import BaseTitleController
	from melon.core.base.formats.base_format.data import BaseTitleData
	from melon.core.base.parser import BaseParser, ParserManifest, ParserSettings
	from melon.core.html.elements import Paragraph
	from melon.core.system_objects.printer import Portals

	from .. import CustomSettingsModel, SourceOperator

class ParserCore:
	"""Content type independent parser core."""

	def __init__(self, parser: "BaseParser", chapter_type: "type[BaseChapter]"):
		"""
		Content type independent parser core.

		Args:
			parser (BaseParser[SourceOperator, CustomSettingsModel, BaseTitleController]): Parser.
			chapter_type (type[BaseChapter]): Chapter type.
		"""

		self._parser: BaseParser[SourceOperator, CustomSettingsModel, BaseTitleController] = parser
		self._chapter_type: type[BaseChapter] = chapter_type

		self._html_parser: HyperTextParser = HyperTextParser(self.settings.common.pretty)
		self._slugger: Slugger = Slugger(self.source_operator)

	def get_age_limit(self, data: dict):
		"""
		Get age limit.

		Args:
			data (dict): Title data.
		"""

		ratigns: dict[int, Literal[0, 16, 18]] = {
			0: 0,
			1: 16,
			2: 18,
		}

		limit: Literal[0, 16, 18] = ratigns[data["age_limit"]["id"]]

		self.data.set_age_limit(limit)

	def get_branches(self, data: dict):
		"""
		Get title branches.

		Args:
			data (dict): Title data.
		"""

		for branch_data in data["branches"]:
			branch_id: int = branch_data["id"]
			branch = Branch(branch_id)
			branch_page: int = 1

			while True:
				params: dict[str, int | str] = {
					"branch_id": branch_id,
					"ordering": "-index",
					"page": branch_page,
				}
				response = self._parser.requestor.get(f"https://{self._parser.manifest.domain}/api/v2/titles/chapters/", params = params)
				branch_page += 1

				if not response.ok or not response.json:
					self.portals.request_error(response, "Unable to request chapter.")

				data: list[dict] = response.json["results"]
				if not data: break

				for chapter_data in data:
					translators: list[str] = [sub["name"] for sub in chapter_data["publishers"]]
					name: str | None = chapter_data["name"] if chapter_data["name"] != "null" else None

					buffer = self._chapter_type(self.parser, chapter_data["id"])
					buffer.set_volume(chapter_data["tome"])
					buffer.set_number(chapter_data["chapter"])
					buffer.set_name(name)
					buffer.set_is_paid(chapter_data["is_paid"])
					buffer.set_workers(translators)

					if self.settings.custom.add_free_publication_date and buffer.is_paid:
						buffer.extra_data.set("free-publication-date", chapter_data["pub_date"])

					branch.add_chapter(buffer)

			branch.reverse()
			self.data.add_branch(branch)

	def get_covers(self, data: dict):
		"""
		Get covers.

		Args:
			data (dict): Title data.
		"""

		covers_data: dict[str, str] = data["cover"]
		covers: list[ImageData] = []

		if self.settings.custom.only_best_cover:
			best_cover_uri = covers_data["high"]
			cover = ImageData(f"https://{self.manifest.domain}{best_cover_uri}", ImageType.Cover)
			covers.append(cover)

		else:
			for cover_uri in reversed(covers_data.values()):
				cover = ImageData(f"https://{self.manifest.domain}{cover_uri}", ImageType.Cover)
				covers.append(cover)

		for cover in covers:
			if cover.link.endswith("/media/None"):
				covers.remove(cover)

		self.data.set_covers(covers)

	def get_description(self, data: dict):
		"""
		Get description.

		Args:
			data (dict): Title data.
		"""

		description: str | None = data.get("description")

		if not description:
			return

		self.data.set_description(self._parse_description(description))

	def get_classificators(self, data: dict, classificator_type: Literal["genres", "categories"]):
		"""
		Get title classificators.

		Args:
			data (dict): Title data.
			classificator_type (Literal["genres", "categories"]): Classificator type.
		"""

		classificators: list[str] = [classificator_data["name"] for classificator_data in data[classificator_type]]

		if classificators:
			setters: dict[Literal["genres", "categories"], Callable] = {
				"genres": self.data.set_genres,
				"categories": self.data.set_tags,
			}

			setters[classificator_type](classificators)

	def get_persons(self):
		"""Get title persons data."""

		persons: list[Person] = []
		response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{self.data.id}/characters/")

		if not response.ok or response.json is None:
			self.portals.request_error(response, "Unable request persons data.")

		for person_data in response.json:
			buffer = Person(person_data["name"])
			buffer.add_another_name(person_data["alt_name"])

			if person_data["cover"]:
				buffer.add_image(ImageData(f"https://{self.manifest.domain}/media/" + person_data["cover"]["high"], ImageType.Person))
				buffer.add_image(ImageData(f"https://{self.manifest.domain}/media/" + person_data["cover"]["mid"], ImageType.Person))

			description: str | None = person_data["description"]

			if description:
				elements: tuple[Paragraph, ...] = self._parse_description(description)
				buffer.set_description(elements)

			persons.append(buffer)

		self.data.set_persons(persons)

	def get_status(self, data: dict):
		"""
		Get title status. Also check licensing by status.

		Args:
			data (dict): Title data.
		"""

		LICENSED_STATUS: str = "Не переводится (лицензировано)"
		status_value: str = data["status"]["name"]

		determinations: dict[str, Status] = {
			"Продолжается": Status.ongoing,
			"Закончен": Status.completed,
			"Анонс": Status.announced,
			"Заморожен": Status.dropped,
			"Нет переводчика": Status.dropped,
			LICENSED_STATUS: Status.dropped,
		}

		if status_value in determinations:
			self.data.set_status(determinations[status_value])

			if status_value == LICENSED_STATUS:
				self.data.set_is_licensed(True)

	def request_title_data(self) -> "WebResponse":
		"""
		Request title data.

		If `Slugger` extension enabled also try to update slug if received HTTP error code 404.

		Returns:
			WebResponse: Response.
		"""

		response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{self.data.slug}/")

		if response.ok or not self.slugger:
			return response

		if self.title.load(self.data.slug):
			self.portals.printer.emit("Loaded local file.")
		else:
			return response

		if self.slugger.update_title_slug(self.data):
			return self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/{self.data.slug}/")

		return response

	def parse_main_data(self) -> dict:
		"""
		Parse main title data.

		Returns:
			dict: Title data.
		"""

		response = self.request_title_data()

		if response.status_code == 404:
			self.portals.title_not_found(self.data)

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable to request title data.")

		data: dict = response.json

		self.data.set_id(data["id"])
		self.data.set_content_language("rus")
		self.data.set_localized_name(data["main_name"])
		self.data.set_eng_name(data["secondary_name"])
		self.data.set_publication_year(data["issue_year"])
		self.data.set_is_licensed(data["is_licensed"])

		if data["another_name"]:
			self.data.set_another_names(str(data["another_name"]).split(" / "))

		self.get_covers(data)
		self.get_description(data)
		self.get_age_limit(data)
		self.get_status(data)
		self.get_classificators(data, "genres")
		self.get_classificators(data, "categories")
		self.get_persons()
		self.get_branches(data)

		return data

	@property
	def data(self) -> "BaseTitleData":
		"""Title data."""

		return self.title.data

	@property
	def html_parser(self) -> HyperTextParser:
		"""HTML elements parser."""

		return self._html_parser

	@property
	def manifest(self) -> "ParserManifest":
		"""Parser manifest."""

		return self._parser.manifest

	@property
	def parser(self) -> "BaseParser[SourceOperator, CustomSettingsModel, BaseTitleController]":
		"""Parser."""

		return self._parser

	@property
	def portals(self) -> "Portals":
		"""Title."""

		return self._parser.portals

	@property
	def requestor(self) -> "WebRequestor":
		"""Requests operator."""

		return self._parser.requestor

	@property
	def settings(self) -> "ParserSettings[CustomSettingsModel]":
		"""Parser settings."""

		return self._parser.settings

	@property
	def slugger(self) -> Slugger:
		"""Slugs updater extension."""

		return self._slugger

	@property
	def source_operator(self) -> "SourceOperator":
		"""Source operator."""

		return self._parser.source_operator

	@property
	def title(self) -> "BaseTitleController[BaseTitleData]":
		"""Title."""

		return self._parser.title

	def _parse_description(self, description: str) -> tuple["Paragraph", ...]:
		"""
		Parse description elements.

		Returns:
			tuple[Paragraph, ...]: Description elements.
		"""

		paragraphs: list[Paragraph] = []
		soup = BeautifulSoup(description, "html.parser")

		for tag in soup.find_all("p", recursive = False):
			paragraphs.extend(self.html_parser.parse_paragraphs(tag, allow_footnotes = False))

		return tuple(paragraphs)

from typing import TYPE_CHECKING, override

from melon.core.base.formats.base_format.branch import Branch
from melon.core.base.formats.manga.chapter import Chapter
from melon.core.base.formats.manga.enums import Type
from melon.core.base.parser.presets import BaseMangaParser
from melon.core.base.structs.image import ImageData, ImageType

from . import extensions
from .modules.core import ParserCore
from .modules.functions import MergeLists

if TYPE_CHECKING:
	from . import SourceOperator as SourceOperator
	from .custom import CustomSettingsModel as CustomSettingsModel
	from .extensions.cards import CardData

class Parser(BaseMangaParser["SourceOperator", "CustomSettingsModel"]):
	"""Parser."""

	@property
	def core(self) -> ParserCore:
		"""Content type independent parser core."""

		return self.__core

	@property
	def exmanga(self) -> extensions.ExManga | None:
		"""Extension: ExManga parser."""

		return self.__exmanga

	@property
	def is_paid_chapters_locked(self) -> bool:
		"""Condition: is paid chapter locked."""

		return self.__is_paid_chapters_locked

	@property
	def slugger(self) -> extensions.Slugger | None:
		"""Extension: title slug updater."""

		return self.__core.slugger

	@override
	def _amend(self, branch: Branch, chapter: Chapter) -> str | None:
		"""
		Amend chapter content.

		Args:
			branch (Branch): Branch.
			chapter (Any): Chapter

		Returns:
			str | None: Optional additional message about amending result.
		"""

		slides: tuple[ImageData, ...] = self.__get_slides(chapter)
		message: str | None = None

		if slides:
			first_slide_link: str = slides[0].link

			if self.exmanga and self.exmanga.domain in first_slide_link:
				message = "Received from ExManga."

			chapter.set_slides(slides)

		return message

	@override
	def _parse(self):
		"""Parse title data witchout chapters content."""

		data: dict = self.core.parse_main_data()

		self.__get_title_type(data)

		if self.source_operator.extensions.is_enabled(extensions.Cards):
			self.title.data.set_extra_data("cards", [], target_key = "persons")

			cards: extensions.Cards = self.source_operator.run_extension(extensions.Cards, force = True)
			cards_data: tuple[CardData, ...] = cards.get_cards_data(data["id"])

			self.portals.printer.emit(f"Cards parsed {len(cards_data)}.")
			self.title.data.set_extra_data("cards", [card_data.to_dict() for card_data in cards_data])

			cards.download_cards(self.title.used_filename, cards_data)
			removed_images_count: int = cards.clear_unused_cards_images(self.title.used_filename, cards_data)

			if removed_images_count:
				self.portals.printer.emit(f"Unused cards images removed: {removed_images_count}.")

	@override
	def _post_init(self):
		"""Execute after instance initialization."""

		self.__is_paid_chapters_locked: bool = False
		self.__core: ParserCore = ParserCore(self, Chapter)
		self.__exmanga: extensions.ExManga | None = self.source_operator.run_extension(extensions.ExManga)

	def __get_slides(self, chapter: Chapter) -> tuple[ImageData, ...]:
		"""
		Get chapter slides.

		Args:
			chapter (Chapter): Chapter.

		Returns:
			tuple[ImageData, ...]: Chapters slides data.
		"""

		slides: list[ImageData] = []

		if chapter.is_paid and self.is_paid_chapters_locked:
			self.portals.chapter_skipped(chapter)
			return ()

		response = self.requestor.get(f"https://{self.manifest.domain}/api/v2/titles/chapters/{chapter.id}/")

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable to request chapter content.")

		data: dict = response.json
		slides_data: list[dict] = MergeLists(data["pages"])

		if not slides_data:
			slides = self.__try_get_chapter_from_exmanga(chapter.id)

			if slides:
				return tuple(slides)

			if chapter.is_paid:
				self._is_paid_chapters_locked = True
				self.portals.printer.debug("Paid chapters locked. All will be skipped.")

			self.portals.chapter_skipped(chapter)
			return ()

		for slide_data in slides_data:
			link: str = slide_data["link"]
			width, height = slide_data["width"], slide_data["height"]
			buffer = ImageData(link, ImageType.Slide)
			buffer.create_resolution(width, height)
			slides.append(buffer)

		return tuple(slides)

	def __get_title_type(self, data: dict):
		"""
		Get title type.

		Args:
			data (dict): Title data.
		"""

		determinations: dict[str, Type] = {
			"Манга": Type.manga,
			"Манхва": Type.manhwa,
			"Маньхуа": Type.manhua,
			"Рукомикс": Type.russian_comic,
			"Западный комикс": Type.western_comic,
			"Индонезийский комикс": Type.indonesian_comic,
		}

		type_value: str = data["type"]["name"]

		if type_value in determinations:
			title_type: Type = determinations[type_value]
			self.title.data.set_title_type(title_type)

	def __try_get_chapter_from_exmanga(self, chapter_id: int) -> list[ImageData]:
		"""
		Try to get chapter slides from ExManga if extension enabled.

		Args:
			chapter_id (int): Chapter ID.

		Returns:
			list[ImageData]: Slides data.
		"""

		if not self.exmanga:
			return []

		slides: list[ImageData] = self.exmanga.get_slides_data(chapter_id)

		if not slides:
			return slides

		filtered_slides: list[ImageData] = []

		for index in range(len(slides)):
			slide: ImageData = slides[index]
			result = self.exmanga.download_slide(self.title, chapter_id, slide)

			if result.filtered_by:
				filtered_slides.append(slide)

		for slide in filtered_slides:
			slides.remove(slide)

		return slides

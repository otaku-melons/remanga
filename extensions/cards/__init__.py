import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

from melon.core.base.extensions import BaseExtension
from melon.core.base.structs.image import ImageData

from .modules.structs import AuthorData, CardData

if TYPE_CHECKING:
	from pathlib import Path

	from ... import SourceOperator as SourceOperator

class Extension(BaseExtension["SourceOperator"]):
	"""Scan slides on images servers."""

	#==========================================================================================#
	# >>>>> PRIVATE METHODS <<<<< #
	#==========================================================================================#

	def __collect_cards_raw_data(self, title_id: int) -> list[dict]:
		"""
		Collect cards raw dictionaries.

		:param title_id: Title ID.
		:type title_id: int
		:return: List of raw cards dictionaries.
		:rtype: list[dict]
		"""

		raw_data: list[dict] = []
		page: int = 1

		while True:
			params: dict = {
				"count": 30,
				"page": page,
			}
			response = self.source_operator.requestor.get(f"https://{self.manifest.domain}/api/inventory/{title_id}/cards/", params = params)

			if not response.ok or not response.json:
				self.portals.request_error(response, "Failed to request card info.")

			results: list[dict] = response.json["results"]
			page += 1

			if results:
				raw_data += results
			else:
				break

		return raw_data

	def __get_cards_directory(self, used_title_name: str) -> "Path":
		"""
		Build and create cards images directory path.

		:param used_title_name: Used title name for cards images directory naming.
		:type used_title_name: str
		:return: Cards images directory path.
		:rtype: Path
		"""

		title_images_directory = self.source_operator.settings.directories.images / used_title_name
		title_images_directory.mkdir(exist_ok = True)
		title_cards_directory = title_images_directory / "cards"
		title_cards_directory.mkdir(exist_ok = True)

		return title_cards_directory

	def __parse_raw_card_data(self, raw_data: dict) -> CardData:
		"""
		Parse card data from raw dictionary.

		:param raw_data: Raw card dictionary.
		:type raw_data: dict
		:return: Card data.
		:rtype: CardData
		"""

		card_id: int = raw_data["id"]

		rank: str = raw_data["rank"]
		rank = rank.replace("rank_", "").upper()

		if rank not in ("S", "A", "B", "C", "D", "E", "F"):
			raise ValueError(f"Unknown rank \"{rank}\".")

		images_uri: list[str] = [
			raw_data["cover"]["high"],
			raw_data["cover"]["mid"],
		]
		if self.source_operator.settings.custom.only_best_cover: images_uri.pop()
		images: list[ImageData] = [ImageData(f"https://{self.manifest.domain}{uri}") for uri in images_uri]

		return CardData(
			id = card_id,
			rank = rank,
			images = images,
			author = AuthorData(raw_data["author"]["id"], raw_data["author"]["username"]),
			person = raw_data["character"]["name"],
		)

	#==========================================================================================#
	# >>>>> PUBLIC METHODS <<<<< #
	#==========================================================================================#

	def clear_unused_cards_images(self, used_title_name: str, cards_data: Sequence[CardData]) -> int:
		"""
		Remove unused images in cards directory.

		:param used_title_name: Used title name for cards images directory naming.
		:type used_title_name: str
		:param cards_data: Cards data sequence.
		:type cards_data: Sequence[CardData]
		:return: Removed images count.
		:rtype: int
		"""

		used_images: list[str] = []

		for card in cards_data:
			for image in card.images:
				used_images.append(image.filename)

		title_cards_directory: Path = self.__get_cards_directory(used_title_name)
		files: list[str] = os.listdir(title_cards_directory)
		images_removed_count: int = 0

		for file in files:
			if file not in used_images:
				os.unlink(title_cards_directory / file)
				images_removed_count += 1

		return images_removed_count

	def download_cards(self, used_title_name: str, cards_data: Sequence[CardData]):
		"""
		Download cards images. Updates images resolutions in data containers.

		:param used_title_name: Used title name for cards images directory naming.
		:type used_title_name: str
		:param cards_data: Cards data sequence.
		:type cards_data: Sequence[CardData]
		"""

		title_cards_directory: Path = self.__get_cards_directory(used_title_name)

		for card in cards_data:
			for image in card.images:
				future = self.portals.printer.templates.images.start_downloading(image.filename)
				result = self.source_operator.download_image(image.link, title_cards_directory)
				future.result(result)

	def get_cards_data(self, title_id: int) -> tuple[CardData, ...]:
		"""
		Request cards data.

		:param title_id: Title ID.
		:type title_id: int
		:return: List of cards data.
		:rtype: tuple[CardData, ...]
		"""

		raw_data: list[dict] = self.__collect_cards_raw_data(title_id)

		return tuple(self.__parse_raw_card_data(data) for data in raw_data)

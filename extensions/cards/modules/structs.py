from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
	from melon.core.base.structs.image import ImageData

@dataclass(frozen = True)
class AuthorData:
	"""Author data."""

	id: int
	username: str

	def to_dict(self) -> dict:
		"""
		Return dictionary representation of object.

		:return: Dictionary representation of object.
		:rtype: dict
		"""

		return {
			"id": self.id,
			"username": self.username
		}

@dataclass(frozen = True)
class CardData:
	"""Card data."""

	id: int
	rank: Literal["S", "A", "B", "C", "D", "E", "F"]
	images: list["ImageData"]
	author: AuthorData
	person: str | None

	def to_dict(self) -> dict:
		"""
		Return dictionary representation of object.

		:return: Dictionary representation of object.
		:rtype: dict
		"""

		return {
			"id": self.id,
			"rank": self.rank,
			"images": [image.to_dict() for image in self.images],
			"author": self.author.to_dict(),
			"person": self.person
		}

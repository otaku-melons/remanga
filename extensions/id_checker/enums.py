from enum import Enum

class BookmarkCreatioinResults(Enum):
	"""Результаты добавления закладки."""

	OK = None
	DENY = "Нельзя добавлять тайтлы в чужие закладки"
	TITLE_ALREADY_IN_GROUP = "Тайтл уже в этом списке"
	TITLE_NOT_FOUND = "Тайтл не найден"
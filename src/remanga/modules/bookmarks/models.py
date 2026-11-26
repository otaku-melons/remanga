from pydantic import BaseModel

class BookmarkTitleModel(BaseModel):
	"""Bookmark title model."""

	id: int
	dir: str

class BookmarkModel(BaseModel):
	"""Bookmark model."""

	id: int
	title: BookmarkTitleModel

class BookmarksGroupModel(BaseModel):
	"""Bookmarks group model."""

	results: tuple[BookmarkModel, ...]

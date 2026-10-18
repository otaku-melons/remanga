from pydantic import BaseModel

class Options(BaseModel):
	"""Extension options model."""

	email: str
	password: str
	use_mirror: bool = False

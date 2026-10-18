from pydantic import BaseModel

class Options(BaseModel):
	"""Extension options model."""

	query: str = "img{or:1-6}{ov:-reserve}.reimg{ov:2}.org"

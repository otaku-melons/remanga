class VariatorValueError(Exception):
	"""Exception: incorrect variator value."""

	def __init__(self, variator: str, message: str):
		"""
		Exception: incorrect variator value.

		:param variator: Variator.
		:type variator: str
		:param message: Error message.
		:type message: str
		"""
		
		super().__init__(f"{variator} {message}")

class UnknownVariatorError(Exception):
	"""Exception: unknown variator."""

	def __init__(self, variator_name: str):
		"""
		Exception: unknown variator.

		:param variator_name: Variator name.
		:type variator_name: str
		"""
		
		super().__init__(variator_name)
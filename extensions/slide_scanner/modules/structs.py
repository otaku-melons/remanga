from dataclasses import dataclass

@dataclass(frozen = True)
class ScanQuery:
	"""Scan query data."""

	query: str
	variants_map: dict[int, tuple[str, ...]]

	@property
	def variants_count(self) -> int:
		"""Count of variants."""

		return sum(len(variants) for variants in self.variants_map.values())


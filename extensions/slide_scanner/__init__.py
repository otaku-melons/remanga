import itertools
import re
from typing import TYPE_CHECKING, override

from melon.core.base.extensions import BaseExtension

from .cli import CLI
from .modules import exceptions
from .modules.structs import ScanQuery
from .options import Options

if TYPE_CHECKING:
	from ... import SourceOperator as SourceOperator

class Extension(BaseExtension["SourceOperator", Options]):
	"""Scan slides on images servers."""

	#==========================================================================================#
	# >>>>> PRIVATE VARIATORS PARSING METHODS <<<<< #
	#==========================================================================================#

	def __make_variants_or(self, variator: str, value: str) -> tuple[str, ...]:
		"""
		Create variants for variator: **or**.

		:param variator: Variator.
		:type variator: str
		:param value: Variator value.
		:type value: str
		:return: Variants.
		:rtype: tuple[str, ...]
		"""

		return ("",) + self.__make_variants_r(variator, value)

	def __make_variants_ov(self, value: str) -> tuple[str, ...]:
		"""
		Create variants for variator: **v**.

		:param value: Variator value.
		:type value: str
		:return: Variants.
		:rtype: tuple[str, ...]
		"""

		return ("",) + self.__make_variants_v(value)

	def __make_variants_r(self, variator: str, value: str) -> tuple[str, ...]:
		"""
		Create variants for variator: **r**.

		:param variator: Variator.
		:type variator: str
		:param value: Variator value.
		:type value: str
		:return: Variants.
		:rtype: tuple[str, ...]
		:raises VariatorValueError: Missing range separator.
		"""

		if "-" not in value:
			raise exceptions.VariatorValueError(variator, "Missing range separator \"-\".")

		parts = value.split("-")
		start: int = int(parts[0])
		end: int = int(parts[1])

		return tuple(str(number) for number in range(start, end + 1))

	def __make_variants_v(self, value: str) -> tuple[str, ...]:
		"""
		Create variants for variator: **v**.

		:param value: Variator value.
		:type value: str
		:return: Variants.
		:rtype: tuple[str, ...]
		"""

		return tuple(value.split(","))

	def __parse_variator(self, variator: str) -> tuple[str, ...]:
		"""
		Make variants from variator.

		:param variator: Variator substring.
		:type variator: str
		:return: Variants.
		:rtype: tuple[str, ...]
		:raises exceptions.VariatorValueError: Incorrect value.
		:raises exceptions.UnknownVariatorError: Variator type not found.
		"""

		if ":" not in variator:
			raise exceptions.VariatorValueError(variator, "No values.")

		if " " in variator or "\t" in variator:
			raise exceptions.VariatorValueError(variator, "Spaces denied.")

		parts: list[str] = variator.split(":", maxsplit = 1)
		name: str = parts[0]
		value: str = parts[1]

		match name:
			case "or": return self.__make_variants_or(variator, value)
			case "ov": return self.__make_variants_ov(value)
			case "r": return self.__make_variants_r(variator, value)
			case "v": return self.__make_variants_v(value)

			case _:
				raise exceptions.UnknownVariatorError(name)

	#==========================================================================================#
	# >>>>> OVERRIDABLE METHODS <<<<< #
	#==========================================================================================#

	@override
	def _export_options_model(self) -> type[Options]:
		"""
		Возвращает модель опций.

		:return: Модель опций.
		:rtype: type[BaseExtensionOptions]
		"""

		return Options

	@override
	def _provide_cli(self) -> type[CLI]:
		"""
		Возвращает класс-обработчик CLI.

		:return: Класс-обработчик CLI.
		:rtype: type[CLI]
		"""

		return CLI

	#==========================================================================================#
	# >>>>> PUBLIC METHODS <<<<< #
	#==========================================================================================#

	def parse_query(self, query: str) -> ScanQuery:
		"""
		Parse scan query from query. Create variants ranges from variators.

		Syntazis is `{variator:params}`. Available variators:
		- r (*range*) – range of unsigned integers. For example `{r:1-3}` gives `("1", "2", "3")`.
		- or (*optional range*) – optional range of unsigned integers. For example `{or:1-3}` gives `("", "1", "2", "3")`.
		- v (*values*) – set of values. For example `{v:one,two}` gives `("one", "two")`.
		- ov (*optional values*) – set of optional values. For example `{v:one,two}` gives `("", "one", "two")`.

		:param query: Quesy string.
		:type query: str
		:return: Scan query data.
		:rtype: ScanQuery
		"""

		variators: list[str] = re.findall(r"\{([^}]+)\}", query)
		variants: dict[int, tuple[str, ...]] = {}

		for index in range(len(variators)):
			variator: str = variators[index]
			variants[index] = self.__parse_variator(variator)
			query = query.replace("{" + variator + "}", f"({index})")

		return ScanQuery(
			query = query,
			variants_map = variants,
		)

	def make_domains_variants(self, query_data: ScanQuery) -> tuple[str, ...]:
		"""
		Create images servers domains tuple from query data.

		:param query_data: Scan query data.
		:type query_data: ScanQuery
		:return: Sorted sequence of domains.
		:rtype: tuple[str, ...]
		"""

		places: list[str] = [f"({index})" for index in query_data.variants_map.keys()]
		domains: list[str] = []

		for combination in itertools.product(*query_data.variants_map.values()):
			current_domain = query_data.query

			for place, variant in zip(places, combination):
				current_domain = current_domain.replace(place, variant)

			domains.append(current_domain)

		return tuple(sorted(domains))



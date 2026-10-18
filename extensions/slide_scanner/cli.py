from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from dublib.cli.text_styler import FastStyler
from dublib.validators import ValidableTypes

from melon.core.base.extensions.cli import BaseExtensionCLI

if TYPE_CHECKING:
	from dublib.cli.terminalyzer import ModelsGroup
	from dublib.cli.terminalyzer.parser.entities import CommandEntity
	from dublib.web_requestor import WebResponse

	from . import Extension as Extension

class CLI(BaseExtensionCLI["Extension"]):
	"""Оператор CLI."""

	#==========================================================================================#
	# >>>>> PRIVATE METHODS <<<<< #
	#==========================================================================================#

	def __stylize_response_code(self, response: "WebResponse") -> str:
		"""
		Stylize response status code.

		:param response: Response.
		:type response: int | None
		:return: Stylized response status code.
		:rtype: str
		"""

		if response.status_code is None:
			return FastStyler("error").colorize.red

		if response.ok:
			return FastStyler(f"{response.status_code} OK").colorize.green

		if response.status_code in (403,):
			return FastStyler(f"{response.status_code}").colorize.yellow

		return FastStyler(str(response.status_code)).colorize.red

	#==========================================================================================#
	# >>>>> PRIVATE COMMANDS HANDLERS <<<<< #
	#==========================================================================================#

	def __handler_scan(self, entity: "CommandEntity"):  # noqa: ARG002
		"""
		Command handler: **scan**.

		:param entity: Command entity.
		:type entity: CommandEntity
		"""

		url: str = entity.get_position_value("URL", expected_type = str, important = True)
		hide_errors: bool = entity.check_flag("-h")

		query: str = self.extension.options.query
		query_data = self.extension.parse_query(query)
		domains: tuple[str, ...] = self.extension.make_domains_variants(query_data)

		self.printer.emit("Scanning…")
		self.extension.source_operator.requestor.config.enable_logging(False)
		ok_count: int = 0

		for domain in domains:
			parsed_url = urlsplit(url)
			updated_url = parsed_url._replace(netloc = domain)
			new_url: str = updated_url.geturl()

			response = self.extension.source_operator.requestor.get(new_url)
			if response.ok: ok_count += 1

			if hide_errors and response.status_code is None:
				continue

			result: str = self.__stylize_response_code(response)
			output: str = f"<i>{domain}</i>: {result}"
			self.printer.emit(output)

		self.printer.emit(f"Scanned {len(domains)} images servers variants.")
		self.printer.emit(f"Image found on {ok_count} servers.")
		
	#==========================================================================================#
	# >>>>> OVERRIDABLE METHODS <<<<< #
	#==========================================================================================#

	def _build_models_group(self, group: "ModelsGroup"):
		"""
		Строит модели команд.

		:param group: Группа, к которой должны принадлежать модели команд.
		:type group: ModelsGroup
		"""

		model = group.create_model("scan", description = "Scan slides on images servers.")
		model.register_handler(self.__handler_scan)
		position = model.create_position("URL", "Image link.", important = True)
		position.set_argument(ValidableTypes.URL)
		model.base.add_flag("-h", description = "Hide domain address resolution errors.")
		
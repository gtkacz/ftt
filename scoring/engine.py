import ast
import operator
from collections.abc import Mapping
from decimal import ROUND_HALF_EVEN, Decimal
from difflib import get_close_matches

from simpleeval import SimpleEval

from scoring.fields import FIELD_CATALOG

MAX_FORMULA_LENGTH = 2000


class FormulaError(ValueError):
	"""A formula failed validation; carries position and a did-you-mean suggestion when known."""

	def __init__(self, message: str, position: int | None = None, suggestion: str | None = None) -> None:
		"""Store the failure message plus optional source position and did-you-mean suggestion."""
		super().__init__(message)
		self.message = message
		self.position = position
		self.suggestion = suggestion


def _safe_div(left: float, right: float) -> float:
	# League semantics: x / 0 is 0, so PTS/MIN never explodes on a DNP line.
	return 0 if right == 0 else left / right


_OPERATORS = {
	ast.Add: operator.add,
	ast.Sub: operator.sub,
	ast.Mult: operator.mul,
	ast.Div: _safe_div,
	ast.USub: operator.neg,
	ast.Lt: operator.lt,
	ast.LtE: operator.le,
	ast.Gt: operator.gt,
	ast.GtE: operator.ge,
	ast.Eq: operator.eq,
	ast.NotEq: operator.ne,
}

_ALLOWED_NODES = (
	ast.Expression,
	ast.BinOp,
	ast.UnaryOp,
	ast.Compare,
	ast.Constant,
	ast.Name,
	ast.Load,
	*(_OPERATORS.keys()),
)


def _check_node(node: ast.AST) -> None:
	"""Raise FormulaError if a single parsed node violates the formula grammar.

	Raises:
		FormulaError: if ``node`` is a chained comparison, a non-numeric literal,
			an unknown field name, or any other disallowed AST node type.
	"""
	if isinstance(node, ast.Compare) and len(node.ops) > 1:
		raise FormulaError("Chained comparisons are not supported.", position=node.col_offset)

	if isinstance(node, ast.Constant):
		if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
			raise FormulaError("Only numeric literals are allowed.", position=node.col_offset)
		return

	if isinstance(node, ast.Name):
		if node.id not in FIELD_CATALOG:
			matches = get_close_matches(node.id, FIELD_CATALOG.keys(), n=1)
			raise FormulaError(
				f"Unknown field '{node.id}'.",
				position=node.col_offset,
				suggestion=matches[0] if matches else None,
			)
		return

	if not isinstance(node, _ALLOWED_NODES):
		raise FormulaError(
			f"'{type(node).__name__}' is not allowed in formulas.",
			position=getattr(node, "col_offset", None),
		)


def validate_formula(text: str) -> None:
	"""Raise FormulaError unless ``text`` is exactly within the league formula grammar.

	Raises:
		FormulaError: if ``text`` is empty, too long, syntactically invalid, references
			an unknown field, or uses any construct outside the formula grammar.
	"""
	if not text or not text.strip():
		raise FormulaError("Formula is empty.")

	if len(text) > MAX_FORMULA_LENGTH:
		raise FormulaError(f"Formula exceeds {MAX_FORMULA_LENGTH} characters.")

	try:
		tree = ast.parse(text, mode="eval")

	except SyntaxError as exc:
		raise FormulaError(f"Syntax error: {exc.msg}.", position=exc.offset) from exc

	for node in ast.walk(tree):
		_check_node(node)


class CompiledFormula:
	"""A validated formula, parsed once, evaluated many times."""

	def __init__(self, text: str) -> None:
		"""Parse ``text`` once via simpleeval so repeated evaluations skip re-parsing."""
		self.text = text
		self._evaluator = SimpleEval(operators=_OPERATORS, functions={})
		self._parsed = self._evaluator.parse(text)

	def evaluate(self, stats: Mapping[str, float]) -> Decimal:
		"""Evaluate the formula against ``stats``, defaulting unset catalog fields to 0.

		Returns:
			The formula result as a Decimal rounded to 2 places (ROUND_HALF_EVEN).
		"""
		names: dict[str, float] = dict.fromkeys(FIELD_CATALOG, 0)
		names.update({key: value for key, value in stats.items() if key in FIELD_CATALOG})
		self._evaluator.names = names
		result = self._evaluator.eval(self.text, previously_parsed=self._parsed)
		return Decimal(str(float(result))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def compile_formula(text: str) -> CompiledFormula:
	"""Validate ``text`` and return a reusable evaluator for it.

	Also smoke-evaluates against an all-zeros line so runtime surprises
	surface at save time, not on game night.

	Raises:
		FormulaError: if ``text`` fails validation or fails the zero-line smoke evaluation.
	"""  # noqa: DOC201
	validate_formula(text)
	compiled = CompiledFormula(text)

	try:
		compiled.evaluate({})

	except FormulaError:
		raise

	except Exception as exc:
		raise FormulaError(f"Formula failed evaluation: {exc}") from exc

	return compiled

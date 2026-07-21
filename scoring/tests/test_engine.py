from decimal import Decimal

from django.test import SimpleTestCase

from scoring.engine import FormulaError, compile_formula, validate_formula


class ValidateFormulaTests(SimpleTestCase):
	def test_accepts_weighted_sum(self) -> None:
		validate_formula("1*PTS + 1.2*OREB + 1.5*AST - 0.5*FT_MISS + 5*DD")

	def test_accepts_comparisons_and_parentheses(self) -> None:
		validate_formula("(PTS >= 40) * 5 + (TO == 0) * 2 - (MIN < 10) * PTS * 0.5")

	def test_accepts_unary_minus(self) -> None:
		validate_formula("-2*TF + -1*TO")

	def test_rejects_empty(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("   ")

	def test_rejects_over_length(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("PTS+" * 600 + "PTS")

	def test_rejects_power(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("PTS ** 2")

	def test_rejects_function_calls(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("min(PTS, 10)")

	def test_rejects_strings(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("PTS + 'x'")

	def test_rejects_boolean_literals(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("PTS + True")

	def test_rejects_attribute_access(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("PTS.real")

	def test_rejects_chained_comparison(self) -> None:
		with self.assertRaises(FormulaError):
			validate_formula("10 < PTS < 20")

	def test_syntax_error_carries_position(self) -> None:
		with self.assertRaises(FormulaError) as ctx:
			validate_formula("1*PTS +")
		self.assertIsNotNone(ctx.exception.position)

	def test_unknown_field_suggests_closest(self) -> None:
		with self.assertRaises(FormulaError) as ctx:
			validate_formula("1*FTMISS")
		self.assertEqual(ctx.exception.suggestion, "FT_MISS")


class EvaluateTests(SimpleTestCase):
	def test_weighted_sum(self) -> None:
		compiled = compile_formula("1*PTS + 2*STL - 1*TO")
		self.assertEqual(compiled.evaluate({"PTS": 20, "STL": 3, "TO": 4}), Decimal("22.00"))

	def test_precedence_and_parentheses(self) -> None:
		compiled = compile_formula("1 + 2 * 3 + (1 + 1) * 2")
		self.assertEqual(compiled.evaluate({}), Decimal("11.00"))

	def test_comparison_is_zero_or_one(self) -> None:
		compiled = compile_formula("(PTS >= 40) * 5")
		self.assertEqual(compiled.evaluate({"PTS": 41}), Decimal("5.00"))
		self.assertEqual(compiled.evaluate({"PTS": 39}), Decimal("0.00"))

	def test_division_by_zero_is_zero(self) -> None:
		compiled = compile_formula("PTS / MIN")
		self.assertEqual(compiled.evaluate({"PTS": 20, "MIN": 0}), Decimal("0.00"))

	def test_missing_fields_default_to_zero(self) -> None:
		compiled = compile_formula("1*PTS + 5*DD")
		self.assertEqual(compiled.evaluate({"PTS": 7}), Decimal("7.00"))

	def test_two_decimal_half_even_rounding(self) -> None:
		compiled = compile_formula("PTS / 8")
		self.assertEqual(compiled.evaluate({"PTS": 1}), Decimal("0.12"))

	def test_extra_unknown_stats_are_ignored(self) -> None:
		compiled = compile_formula("1*PTS")
		self.assertEqual(compiled.evaluate({"PTS": 3, "GARBAGE": 99}), Decimal("3.00"))

	def test_compile_smoke_evaluates_against_zero_line(self) -> None:
		# compile_formula must survive an all-zeros line (safe division makes this total 0).
		compiled = compile_formula("PTS / MIN + AST / FTA")
		self.assertEqual(compiled.evaluate({}), Decimal("0.00"))

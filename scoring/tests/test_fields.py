from django.test import SimpleTestCase

from scoring.fields import FIELD_CATALOG, derive_fields


class FieldCatalogTests(SimpleTestCase):
	def test_catalog_has_27_fields(self) -> None:
		self.assertEqual(len(FIELD_CATALOG), 27)

	def test_names_are_valid_python_identifiers(self) -> None:
		for name in FIELD_CATALOG:
			self.assertTrue(name.isidentifier(), name)

	def test_sources_are_known(self) -> None:
		for spec in FIELD_CATALOG.values():
			self.assertIn(spec.source, ("box", "derived", "pbp", "context"))

	def test_catalog_keys_match_spec_names(self) -> None:
		for name, spec in FIELD_CATALOG.items():
			self.assertEqual(name, spec.name)


class DeriveFieldsTests(SimpleTestCase):
	def test_misses_are_attempts_minus_makes(self) -> None:
		out = derive_fields({"FGA": 18, "FGM": 9, "TPA": 8, "TPM": 3, "FTA": 5, "FTM": 4})
		self.assertEqual(out["FG_MISS"], 9)
		self.assertEqual(out["TP_MISS"], 5)
		self.assertEqual(out["FT_MISS"], 1)

	def test_double_double_requires_two_tens(self) -> None:
		out = derive_fields({"PTS": 10, "REB": 10, "AST": 9, "STL": 0, "BLK": 0})
		self.assertEqual(out["DD"], 1)
		self.assertEqual(out["TD"], 0)

	def test_triple_double_also_counts_as_double_double(self) -> None:
		out = derive_fields({"PTS": 10, "REB": 11, "AST": 12, "STL": 0, "BLK": 0})
		self.assertEqual(out["DD"], 1)
		self.assertEqual(out["TD"], 1)

	def test_nine_is_not_ten(self) -> None:
		out = derive_fields({"PTS": 30, "REB": 9, "AST": 9, "STL": 1, "BLK": 1})
		self.assertEqual(out["DD"], 0)
		self.assertEqual(out["TD"], 0)

	def test_missing_keys_default_to_zero(self) -> None:
		out = derive_fields({})
		self.assertEqual(out["FG_MISS"], 0)
		self.assertEqual(out["DD"], 0)

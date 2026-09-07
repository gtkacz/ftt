# Scoring Rule Builder & Live Stat Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give FTT its own fantasy scoring: a 27-field ESPN stat catalog, a superuser-built formula engine (simpleeval), a live/settle/corrections ingest worker, and a Vue builder UI with live preview — so the league no longer depends on Fantrax's math.

**Architecture:** Stats are facts, points are a pure function of facts. A new `scoring` Django app ingests ESPN box scores + play-by-play into `PlayerGameLine.raw_stats`; a single mutable `ScoringRule` (formula text, simpleeval-evaluated) derives `fpts`; recompute, corrections, and rule edits share that one code path. A Vue builder view (superuser-only) edits the rule via a weights grid or formula editor with server-side preview.

**Tech Stack:** Django 5 + DRF + drf-spectacular (existing), simpleeval (new dep), Django test runner, requests; Vue 3 `<script setup>` + TS + Vuetify 3 + Pinia (existing, no new frontend deps).

**Spec:** `docs/superpowers/specs/2026-07-20-scoring-rule-builder-design.md` (read it first).

## Global Constraints

- Backend repo: `/home/gtkacz/Codes/ftt/ftt-server` (its own git repo). Frontend repo: `/home/gtkacz/Codes/ftt/ftt-app` (its own git repo) — Tasks 10–11 commit there.
- Python style: **tabs**, double quotes, type annotations on signatures (project convention). Run `ruff check --fix && ruff format` from `ftt-server/` after each backend task; fix what it reports before committing.
- Tests: Django test runner. Run: `.venv/bin/python manage.py test scoring -v 2` from `ftt-server/`. No pytest.
- Timezone: settings use `America/Sao_Paulo`, `USE_TZ=True`. NBA calendar dates must be computed in `America/New_York` (see `et_today()` in Task 4).
- Formula grammar (exact): int/float literals, catalog field names, `+ - * /`, parentheses, unary minus, and `< <= > >= == !=` evaluating to 0/1. Nothing else — no functions, strings, booleans, power, chained comparisons.
- Division is safe: `x / 0 → 0`.
- Formula length cap: 2000 characters.
- `fpts` policy: evaluate in float → `Decimal` quantized to 2dp with `ROUND_HALF_EVEN`.
- Exactly one `ScoringRule` may have `is_active=True` (DB partial unique constraint).
- DD/TD stack: a triple-double game has `DD=1` **and** `TD=1`.
- Write endpoints are superuser-only (`request.user.is_superuser`).
- Commits: conventional format (`feat:`, `test:`, `docs:`, `chore:`), no attribution footers, commit on the current branch (no feature branches).
- Frontend style: 2-space indent, double quotes, `Service` object modules in `src/api/`, options-style Pinia stores. Verify with `bun run lintbuild` (runs `vue-tsc -b && vite build`).

## File structure

```
ftt-server/
  scoring/
    __init__.py  apps.py  admin.py
    fields.py                      # FieldSpec registry + derive_fields (Task 1)
    engine.py                      # validate/compile/evaluate via simpleeval (Task 2)
    permissions.py                 # IsSuperUser (Task 8)
    serializers.py  views.py  urls.py            (Task 8)
    models/
      __init__.py  scoring_rule.py  scoring_period.py  nba_game.py
      player_game_line.py  stat_correction.py    (Task 3)
    services/
      __init__.py
      espn.py                      # HTTP client + snapshots (Task 4)
      extract.py                   # summary JSON → GameInfo/PlayerLine (Task 4)
      periods.py                   # week generation/closing (Task 5)
      ingest.py                    # upsert lines, recompute (Task 5)
      settle.py                    # box hashing (Task 6)
      corrections.py               # T+1 sweep (Task 7)
      crosswalk.py                 # name matching → Player.espn_id (Task 9)
    management/commands/
      live_scoring_worker.py       (Task 6)
      backfill_season.py           (Task 9)
      parity_check.py              (Task 9)
    tests/
      __init__.py  test_fields.py  test_engine.py  test_models.py
      test_extract.py  test_ingest.py  test_worker.py
      test_corrections.py  test_api.py  test_crosswalk.py
      fixtures/espn_summary_401859966.json  fixtures/espn_scoreboard_finals_2026.json
  core/models/player.py            # + espn_id (Task 3)
  ftt/settings.py                  # + INSTALLED_APPS entry (Task 1)
  ftt/urls.py                      # + scoring include (Task 8)
  requirements.in / requirements.txt   # + simpleeval (Task 2)

ftt-app/src/
  types/scoring.ts  api/scoring.ts  stores/scoring.ts          (Task 10)
  components/scoring/FieldPalette.vue  WeightsGrid.vue
  components/scoring/FormulaEditor.vue  PreviewPanel.vue        (Task 11)
  views/admin/ScoringRuleBuilderView.vue                        (Task 11)
  router/index.ts  components/layout/navItems.ts                (Task 11)
```

---

### Task 1: `scoring` app scaffold + field catalog

**Files:**
- Create: `scoring/__init__.py`, `scoring/apps.py`, `scoring/admin.py` (empty), `scoring/migrations/__init__.py`, `scoring/fields.py`, `scoring/tests/__init__.py`, `scoring/tests/test_fields.py`
- Modify: `ftt/settings.py` (INSTALLED_APPS)

**Interfaces:**
- Produces: `scoring.fields.FIELD_CATALOG: dict[str, FieldSpec]` (27 entries), `scoring.fields.FieldSpec` (NamedTuple: `name, label, description, example, source`), `scoring.fields.derive_fields(stats: dict[str, float]) -> dict[str, float]`.

- [ ] **Step 1: Scaffold the app**

`scoring/__init__.py` and `scoring/admin.py`: empty files. `scoring/migrations/__init__.py`: empty file.

`scoring/apps.py`:

```python
from django.apps import AppConfig


class ScoringConfig(AppConfig):
	default_auto_field = "django.db.models.BigAutoField"
	name = "scoring"
```

In `ftt/settings.py`, INSTALLED_APPS, add `"scoring",` directly after `"trade",`.

- [ ] **Step 2: Write the failing tests**

`scoring/tests/__init__.py`: empty file. `scoring/tests/test_fields.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.fields'`

- [ ] **Step 4: Implement `scoring/fields.py`**

```python
from typing import Literal, NamedTuple


class FieldSpec(NamedTuple):
	"""One stat field exposed to scoring formulas; drives ingest, engine names, and the UI palette."""

	name: str
	label: str
	description: str
	example: float
	source: Literal["box", "derived", "pbp", "context"]


_BOX = (
	FieldSpec("MIN", "MIN", "Minutes played", 33, "box"),
	FieldSpec("PTS", "PTS", "Points scored", 25, "box"),
	FieldSpec("FGM", "FG made", "Field goals made", 9, "box"),
	FieldSpec("FGA", "FG att.", "Field goals attempted", 18, "box"),
	FieldSpec("TPM", "3PT made", "Three-pointers made (display: 3PM)", 3, "box"),
	FieldSpec("TPA", "3PT att.", "Three-pointers attempted (display: 3PA)", 8, "box"),
	FieldSpec("FTM", "FT made", "Free throws made", 4, "box"),
	FieldSpec("FTA", "FT att.", "Free throws attempted", 5, "box"),
	FieldSpec("OREB", "Off. reb.", "Offensive rebounds", 2, "box"),
	FieldSpec("DREB", "Def. reb.", "Defensive rebounds", 6, "box"),
	FieldSpec("REB", "Rebounds", "Total rebounds", 8, "box"),
	FieldSpec("AST", "Assists", "Assists", 7, "box"),
	FieldSpec("STL", "Steals", "Steals", 2, "box"),
	FieldSpec("BLK", "Blocks", "Blocks", 1, "box"),
	FieldSpec("TO", "Turnovers", "Turnovers", 3, "box"),
	FieldSpec("PF", "Fouls", "Personal fouls", 2, "box"),
	FieldSpec("PLUS_MINUS", "+/-", "Plus-minus while on court", -4, "box"),
)

_DERIVED = (
	FieldSpec("FG_MISS", "FG missed", "Field goals missed (FGA - FGM)", 9, "derived"),
	FieldSpec("TP_MISS", "3PT missed", "Three-pointers missed (TPA - TPM)", 5, "derived"),
	FieldSpec("FT_MISS", "FT missed", "Free throws missed (FTA - FTM)", 1, "derived"),
	FieldSpec(
		"DD",
		"Double-double",
		"1 if at least two of PTS/REB/AST/STL/BLK reached 10 (a triple-double also counts)",
		0,
		"derived",
	),
	FieldSpec("TD", "Triple-double", "1 if at least three of PTS/REB/AST/STL/BLK reached 10", 0, "derived"),
)

_PBP = (
	FieldSpec("TF", "Tech. fouls", "Technical fouls, from play-by-play", 0, "pbp"),
	FieldSpec("FLAGRANT", "Flagrant fouls", "Flagrant fouls, from play-by-play", 0, "pbp"),
	FieldSpec("EJECTION", "Ejections", "Ejections, from play-by-play", 0, "pbp"),
)

_CONTEXT = (
	FieldSpec("STARTED", "Started", "1 if the player started the game", 1, "context"),
	FieldSpec("WON", "Team won", "1 if the player's NBA team won the game", 1, "context"),
)

FIELD_CATALOG: dict[str, FieldSpec] = {spec.name: spec for spec in (*_BOX, *_DERIVED, *_PBP, *_CONTEXT)}

_TEN_CATEGORIES = ("PTS", "REB", "AST", "STL", "BLK")


def derive_fields(stats: dict[str, float]) -> dict[str, float]:
	"""Return a copy of ``stats`` with the derived catalog fields filled in."""
	out = dict(stats)
	out["FG_MISS"] = out.get("FGA", 0) - out.get("FGM", 0)
	out["TP_MISS"] = out.get("TPA", 0) - out.get("TPM", 0)
	out["FT_MISS"] = out.get("FTA", 0) - out.get("FTM", 0)
	tens = sum(1 for key in _TEN_CATEGORIES if out.get(key, 0) >= 10)
	out["DD"] = 1 if tens >= 2 else 0
	out["TD"] = 1 if tens >= 3 else 0
	return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring -v 2`
Expected: PASS (9 tests)

- [ ] **Step 6: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/ ftt/settings.py
git commit -m "feat: add scoring app with 27-field ESPN stat catalog"
```

---

### Task 2: formula engine (simpleeval)

**Files:**
- Create: `scoring/engine.py`, `scoring/tests/test_engine.py`
- Modify: `requirements.in`, `requirements.txt`

**Interfaces:**
- Consumes: `scoring.fields.FIELD_CATALOG`.
- Produces: `scoring.engine.FormulaError(ValueError)` with attrs `message: str`, `position: int | None`, `suggestion: str | None`; `scoring.engine.validate_formula(text: str) -> None`; `scoring.engine.compile_formula(text: str) -> CompiledFormula`; `CompiledFormula.evaluate(stats: Mapping[str, float]) -> Decimal` (2dp); `scoring.engine.MAX_FORMULA_LENGTH = 2000`.

- [ ] **Step 1: Install and pin simpleeval**

```bash
uv pip install --python .venv/bin/python simpleeval
.venv/bin/python -c "import simpleeval; print(simpleeval.__name__, 'ok')"
```

Append `simpleeval` on its own line to `requirements.in`. Then pin the exact installed version in `requirements.txt` (keep the file's existing style):

```bash
.venv/bin/python -m pip show simpleeval | head -2   # note the version, e.g. 1.0.3
```

Add `simpleeval==<that version>` to `requirements.txt`.

- [ ] **Step 2: Write the failing tests**

`scoring/tests/test_engine.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_engine -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.engine'`

- [ ] **Step 4: Implement `scoring/engine.py`**

```python
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


def validate_formula(text: str) -> None:
	"""Raise FormulaError unless ``text`` is exactly within the league formula grammar."""
	if not text or not text.strip():
		raise FormulaError("Formula is empty.")

	if len(text) > MAX_FORMULA_LENGTH:
		raise FormulaError(f"Formula exceeds {MAX_FORMULA_LENGTH} characters.")

	try:
		tree = ast.parse(text, mode="eval")

	except SyntaxError as exc:
		raise FormulaError(f"Syntax error: {exc.msg}.", position=exc.offset) from exc

	for node in ast.walk(tree):
		if isinstance(node, ast.Compare) and len(node.ops) > 1:
			raise FormulaError("Chained comparisons are not supported.", position=node.col_offset)

		if isinstance(node, ast.Constant):
			if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
				raise FormulaError("Only numeric literals are allowed.", position=node.col_offset)

		elif isinstance(node, ast.Name):
			if node.id not in FIELD_CATALOG:
				matches = get_close_matches(node.id, FIELD_CATALOG.keys(), n=1)
				raise FormulaError(
					f"Unknown field '{node.id}'.",
					position=node.col_offset,
					suggestion=matches[0] if matches else None,
				)

		elif not isinstance(node, _ALLOWED_NODES):
			raise FormulaError(
				f"'{type(node).__name__}' is not allowed in formulas.",
				position=getattr(node, "col_offset", None),
			)


class CompiledFormula:
	"""A validated formula, parsed once, evaluated many times."""

	def __init__(self, text: str) -> None:
		self.text = text
		self._evaluator = SimpleEval(operators=_OPERATORS, functions={})
		self._parsed = self._evaluator.parse(text)

	def evaluate(self, stats: Mapping[str, float]) -> Decimal:
		names: dict[str, float] = dict.fromkeys(FIELD_CATALOG, 0)
		names.update({key: value for key, value in stats.items() if key in FIELD_CATALOG})
		self._evaluator.names = names
		result = self._evaluator.eval(self.text, previously_parsed=self._parsed)
		return Decimal(str(float(result))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def compile_formula(text: str) -> CompiledFormula:
	"""Validate ``text`` and return a reusable evaluator for it.

	Also smoke-evaluates against an all-zeros line so runtime surprises
	surface at save time, not on game night.
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_engine -v 2`
Expected: PASS (21 tests). If `eval(..., previously_parsed=...)` raises `TypeError` on the installed simpleeval version, replace that call with `self._evaluator.eval(self.text)` (still correct, just re-parses).

- [ ] **Step 6: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/engine.py scoring/tests/test_engine.py requirements.in requirements.txt
git commit -m "feat: add formula engine with validated grammar over simpleeval"
```

---

### Task 3: models + migrations

**Files:**
- Create: `scoring/models/__init__.py`, `scoring/models/scoring_rule.py`, `scoring/models/scoring_period.py`, `scoring/models/nba_game.py`, `scoring/models/player_game_line.py`, `scoring/models/stat_correction.py`, `scoring/tests/test_models.py`
- Modify: `core/models/player.py`
- Generated: `scoring/migrations/0001_initial.py`, `core/migrations/00XX_player_espn_id.py`

**Interfaces:**
- Consumes: `scoring.engine.validate_formula`, `core.models.NBATeam`, `core.models.Player`, `settings.AUTH_USER_MODEL`.
- Produces: models `ScoringRule(name, formula_text, weights_json, is_active, updated_by, created_at, updated_at)`, `ScoringPeriod(index, starts_at, ends_at, is_closed)` + classmethod `ScoringPeriod.for_datetime(dt) -> ScoringPeriod | None`, `NbaGame(espn_event_id, starts_at, home, away, status, period, clock, settle_hash, scoring_period)` with `STATUS_*` constants, `PlayerGameLine(player, game, raw_stats, fpts, is_final, updated_at)`, `StatCorrection(line, field, old_value, new_value, applied, detected_at)`; `Player.espn_id`.

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_models.py`:

```python
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import NBATeam, Player
from scoring.engine import FormulaError
from scoring.models import NbaGame, PlayerGameLine, ScoringPeriod, ScoringRule


class ScoringRuleTests(TestCase):
	def test_save_rejects_invalid_formula(self) -> None:
		rule = ScoringRule(name="bad", formula_text="1*NOPE")
		with self.assertRaises(FormulaError):
			rule.save()

	def test_only_one_active_rule(self) -> None:
		ScoringRule.objects.create(name="a", formula_text="1*PTS", is_active=True)
		with self.assertRaises(IntegrityError), transaction.atomic():
			ScoringRule.objects.create(name="b", formula_text="1*PTS", is_active=True)

	def test_many_inactive_rules_allowed(self) -> None:
		ScoringRule.objects.create(name="a", formula_text="1*PTS")
		ScoringRule.objects.create(name="b", formula_text="1*PTS")
		self.assertEqual(ScoringRule.objects.count(), 2)


class ScoringPeriodTests(TestCase):
	def test_for_datetime_finds_containing_period(self) -> None:
		now = timezone.now()
		period = ScoringPeriod.objects.create(
			index=1, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=6)
		)
		self.assertEqual(ScoringPeriod.for_datetime(now), period)
		self.assertIsNone(ScoringPeriod.for_datetime(now + timedelta(days=30)))


class PlayerGameLineTests(TestCase):
	def setUp(self) -> None:
		self.team = NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		self.player = Player.objects.create(
			first_name="Julian", last_name="Champagnie", primary_position="F", espn_id="4433134"
		)
		self.game = NbaGame.objects.create(
			espn_event_id="401859966", starts_at=timezone.now(), home=self.team, away=self.team
		)

	def test_line_unique_per_player_and_game(self) -> None:
		PlayerGameLine.objects.create(player=self.player, game=self.game, raw_stats={"PTS": 5})
		with self.assertRaises(IntegrityError), transaction.atomic():
			PlayerGameLine.objects.create(player=self.player, game=self.game, raw_stats={"PTS": 6})

	def test_espn_id_unique_on_player(self) -> None:
		with self.assertRaises(IntegrityError), transaction.atomic():
			Player.objects.create(first_name="Copy", last_name="Cat", primary_position="G", espn_id="4433134")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_models -v 2`
Expected: FAIL — `ImportError: cannot import name 'NbaGame' from 'scoring.models'`

- [ ] **Step 3: Implement the models**

`core/models/player.py` — add after the `nba_id` field (keep everything else untouched):

```python
	espn_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
```

`scoring/models/scoring_rule.py`:

```python
from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.db import models

from scoring.engine import validate_formula


class ScoringRule(models.Model):
	"""The league scoring formula. Exactly one rule may be active; edits recompute the season."""

	name = models.CharField(max_length=100)
	formula_text = models.TextField()
	weights_json = models.JSONField(
		null=True, blank=True, help_text="Grid-mode weights, kept only for round-trip editing"
	)
	is_active = models.BooleanField(default=False)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="scoring_rules"
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = (
			models.UniqueConstraint(
				fields=("is_active",),
				condition=models.Q(is_active=True),
				name="unique_active_scoring_rule",
			),
		)

	def __str__(self) -> str:
		return f"{self.name}{' (active)' if self.is_active else ''}"

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # noqa: D102
		validate_formula(self.formula_text)
		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]
```

`scoring/models/scoring_period.py`:

```python
from datetime import datetime

from django.db import models


class ScoringPeriod(models.Model):
	"""One matchup week (Mon-Sun). Corrections apply only while the period is open."""

	index = models.PositiveIntegerField(unique=True)
	starts_at = models.DateTimeField()
	ends_at = models.DateTimeField()
	is_closed = models.BooleanField(default=False)

	class Meta:
		ordering = ("index",)

	def __str__(self) -> str:
		return f"Week {self.index}"

	@classmethod
	def for_datetime(cls, dt: datetime) -> "ScoringPeriod | None":
		"""Return the period containing ``dt``, if any."""  # noqa: DOC201
		return cls.objects.filter(starts_at__lte=dt, ends_at__gt=dt).first()
```

`scoring/models/nba_game.py`:

```python
from django.db import models


class NbaGame(models.Model):
	"""One real NBA game tracked from ESPN."""

	STATUS_SCHEDULED = "scheduled"
	STATUS_LIVE = "live"
	STATUS_FINAL = "final"
	STATUS_SETTLED = "settled"
	STATUS_CHOICES = (
		(STATUS_SCHEDULED, "Scheduled"),
		(STATUS_LIVE, "Live"),
		(STATUS_FINAL, "Final (box not yet stable)"),
		(STATUS_SETTLED, "Settled"),
	)

	espn_event_id = models.CharField(max_length=20, unique=True)
	starts_at = models.DateTimeField()
	home = models.ForeignKey("core.NBATeam", on_delete=models.SET_NULL, null=True, related_name="home_games")
	away = models.ForeignKey("core.NBATeam", on_delete=models.SET_NULL, null=True, related_name="away_games")
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
	period = models.PositiveSmallIntegerField(default=0)
	clock = models.CharField(max_length=10, blank=True)
	settle_hash = models.CharField(
		max_length=64, blank=True, help_text="SHA-256 of the last fetched box, for stability detection"
	)
	scoring_period = models.ForeignKey(
		"scoring.ScoringPeriod", on_delete=models.SET_NULL, null=True, blank=True, related_name="games"
	)

	class Meta:
		ordering = ("starts_at",)

	def __str__(self) -> str:
		return f"{self.away} @ {self.home} ({self.espn_event_id})"
```

`scoring/models/player_game_line.py`:

```python
from django.db import models


class PlayerGameLine(models.Model):
	"""A player's raw stat line for one game plus the derived fantasy points."""

	player = models.ForeignKey("core.Player", on_delete=models.CASCADE, related_name="game_lines")
	game = models.ForeignKey("scoring.NbaGame", on_delete=models.CASCADE, related_name="lines")
	raw_stats = models.JSONField(default=dict)
	fpts = models.DecimalField(max_digits=8, decimal_places=2, default=0)
	is_final = models.BooleanField(default=False)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = (models.UniqueConstraint(fields=("player", "game"), name="unique_line_per_player_game"),)

	def __str__(self) -> str:
		return f"{self.player} @ {self.game_id}: {self.fpts}"
```

`scoring/models/stat_correction.py`:

```python
from django.db import models


class StatCorrection(models.Model):
	"""An observed post-settlement stat diff; applied only while the scoring period was open."""

	line = models.ForeignKey("scoring.PlayerGameLine", on_delete=models.CASCADE, related_name="corrections")
	field = models.CharField(max_length=20)
	old_value = models.FloatField()
	new_value = models.FloatField()
	applied = models.BooleanField(default=False)
	detected_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.line}: {self.field} {self.old_value} -> {self.new_value}"
```

`scoring/models/__init__.py`:

```python
from scoring.models.nba_game import NbaGame
from scoring.models.player_game_line import PlayerGameLine
from scoring.models.scoring_period import ScoringPeriod
from scoring.models.scoring_rule import ScoringRule
from scoring.models.stat_correction import StatCorrection

__all__ = ("NbaGame", "PlayerGameLine", "ScoringPeriod", "ScoringRule", "StatCorrection")
```

- [ ] **Step 4: Make and run migrations**

```bash
.venv/bin/python manage.py makemigrations core scoring
.venv/bin/python manage.py migrate
```

Expected: `core` migration adds `espn_id`; `scoring` gets `0001_initial`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_models -v 2`
Expected: PASS (6 tests)

- [ ] **Step 6: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/ core/models/player.py core/migrations/
git commit -m "feat: add scoring models and player espn_id"
```

---

### Task 4: ESPN client + extractors (with real fixtures)

**Files:**
- Create: `scoring/services/__init__.py` (empty), `scoring/services/espn.py`, `scoring/services/extract.py`, `scoring/tests/test_extract.py`, `scoring/tests/fixtures/espn_summary_401859966.json`, `scoring/tests/fixtures/espn_scoreboard_finals_2026.json`

**Interfaces:**
- Consumes: `scoring.fields.derive_fields`.
- Produces: `espn.fetch_scoreboard(day: date | None = None) -> dict`, `espn.fetch_summary(event_id: str) -> dict`, `espn.save_snapshot(payload: dict, event_id: str) -> Path`, `espn.et_today() -> date`, `espn.ET` (ZoneInfo); `extract.GameInfo` (frozen dataclass: `event_id: str, starts_at: datetime, state: str, period: int, clock: str, home_abbr: str, away_abbr: str`), `extract.PlayerLine` (frozen dataclass: `espn_id: str, display_name: str, team_abbr: str, stats: dict[str, float]`), `extract.extract_games(scoreboard: dict) -> list[GameInfo]`, `extract.extract_player_lines(summary: dict) -> list[PlayerLine]`.

- [ ] **Step 1: Record the fixtures (one-time network step)**

```bash
mkdir -p scoring/tests/fixtures
curl -s -m 30 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401859966' \
  -o scoring/tests/fixtures/espn_summary_401859966.json
curl -s -m 30 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260601-20260630&limit=50' \
  -o scoring/tests/fixtures/espn_scoreboard_finals_2026.json
.venv/bin/python - <<'CHECK'
import json
summary = json.load(open("scoring/tests/fixtures/espn_summary_401859966.json"))
scoreboard = json.load(open("scoring/tests/fixtures/espn_scoreboard_finals_2026.json"))
assert "boxscore" in summary and "plays" in summary, "summary fixture incomplete"
assert len(scoreboard.get("events", [])) == 5, "expected the five 2026 Finals games"
print("fixtures ok")
CHECK
```

Expected: `fixtures ok`. These are finished 2026 Finals payloads — stable, safe to commit (~600 KB total).

- [ ] **Step 2: Write the failing tests**

`scoring/tests/test_extract.py`:

```python
import json
from pathlib import Path

from django.test import SimpleTestCase

from scoring.fields import FIELD_CATALOG
from scoring.services import extract

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
	return json.loads((FIXTURES / name).read_text())


class ExtractGamesTests(SimpleTestCase):
	def test_finals_scoreboard_has_five_completed_games(self) -> None:
		games = extract.extract_games(load_fixture("espn_scoreboard_finals_2026.json"))
		self.assertEqual(len(games), 5)
		self.assertIn("401859966", [game.event_id for game in games])
		for game in games:
			self.assertEqual(game.state, "post")
			self.assertTrue(game.home_abbr)
			self.assertTrue(game.away_abbr)
			self.assertIsNotNone(game.starts_at.tzinfo)


class ExtractPlayerLinesTests(SimpleTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		cls.lines = extract.extract_player_lines(load_fixture("espn_summary_401859966.json"))
		cls.by_name = {line.display_name: line for line in cls.lines}

	def test_every_line_has_the_full_catalog(self) -> None:
		self.assertGreater(len(self.lines), 15)
		for line in self.lines:
			self.assertEqual(set(line.stats), set(FIELD_CATALOG), line.display_name)

	def test_champagnie_box_line_matches_espn(self) -> None:
		stats = self.by_name["Julian Champagnie"].stats
		expected = {
			"MIN": 33,
			"PTS": 5,
			"FGM": 2,
			"FGA": 9,
			"TPM": 1,
			"TPA": 7,
			"FTM": 0,
			"FTA": 0,
			"REB": 5,
			"AST": 3,
			"TO": 0,
			"STL": 4,
			"BLK": 0,
			"OREB": 0,
			"DREB": 5,
			"PF": 1,
			"PLUS_MINUS": -4,
			"FG_MISS": 7,
			"TP_MISS": 6,
			"FT_MISS": 0,
			"DD": 0,
			"TD": 0,
		}
		for key, value in expected.items():
			self.assertEqual(stats[key], value, key)

	def test_technical_fouls_are_attributed_from_play_by_play(self) -> None:
		self.assertGreaterEqual(self.by_name["Keldon Johnson"].stats["TF"], 1)
		self.assertGreaterEqual(self.by_name["Landry Shamet"].stats["TF"], 1)

	def test_technical_free_throws_are_not_technical_fouls(self) -> None:
		# Karl-Anthony Towns made a technical free throw in this game; that is not a TF against him.
		made_tf_free_throw = self.by_name["Karl-Anthony Towns"].stats["TF"]
		self.assertEqual(made_tf_free_throw, 0)

	def test_exactly_one_team_won(self) -> None:
		winners = {line.team_abbr for line in self.lines if line.stats["WON"] == 1}
		losers = {line.team_abbr for line in self.lines if line.stats["WON"] == 0}
		self.assertEqual(len(winners), 1)
		self.assertEqual(len(losers), 1)

	def test_starters_are_flagged(self) -> None:
		self.assertEqual(sum(1 for line in self.lines if line.stats["STARTED"] == 1), 10)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_extract -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.services'`

- [ ] **Step 4: Implement `scoring/services/espn.py`**

```python
import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils import timezone

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ET = ZoneInfo("America/New_York")

_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) ftt-live-scoring"}
_TIMEOUT_SECONDS = 20


def et_today() -> date:
	"""NBA schedule days are US Eastern calendar dates, not local ones."""  # noqa: DOC201
	return timezone.now().astimezone(ET).date()


def fetch_scoreboard(day: date | None = None) -> dict:
	"""Fetch the scoreboard for ``day`` (ET); ESPN defaults to the nearest game day when omitted."""  # noqa: DOC201
	params = {"dates": day.strftime("%Y%m%d")} if day else {}
	response = requests.get(f"{BASE_URL}/scoreboard", params=params, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
	response.raise_for_status()
	return response.json()


def fetch_summary(event_id: str) -> dict:
	"""Fetch the full game summary (box score, plays, win probability)."""  # noqa: DOC201
	response = requests.get(
		f"{BASE_URL}/summary", params={"event": event_id}, headers=_HEADERS, timeout=_TIMEOUT_SECONDS
	)
	response.raise_for_status()
	return response.json()


def save_snapshot(payload: dict, event_id: str) -> Path:
	"""Persist raw ESPN JSON to MEDIA_ROOT for replay and debugging."""  # noqa: DOC201
	now = timezone.now().astimezone(ET)
	directory = Path(settings.MEDIA_ROOT) / "espn_snapshots" / now.strftime("%Y-%m-%d")
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / f"{event_id}_{now.strftime('%H%M%S')}.json"
	path.write_text(json.dumps(payload))
	return path
```

- [ ] **Step 5: Implement `scoring/services/extract.py`**

```python
from dataclasses import dataclass
from datetime import datetime

from scoring.fields import derive_fields

_PAIR_KEYS = {
	"fieldGoalsMade-fieldGoalsAttempted": ("FGM", "FGA"),
	"threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("TPM", "TPA"),
	"freeThrowsMade-freeThrowsAttempted": ("FTM", "FTA"),
}

_SCALAR_KEYS = {
	"minutes": "MIN",
	"points": "PTS",
	"rebounds": "REB",
	"assists": "AST",
	"turnovers": "TO",
	"steals": "STL",
	"blocks": "BLK",
	"offensiveRebounds": "OREB",
	"defensiveRebounds": "DREB",
	"fouls": "PF",
	"plusMinus": "PLUS_MINUS",
}


@dataclass(frozen=True)
class GameInfo:
	event_id: str
	starts_at: datetime
	state: str
	period: int
	clock: str
	home_abbr: str
	away_abbr: str


@dataclass(frozen=True)
class PlayerLine:
	espn_id: str
	display_name: str
	team_abbr: str
	stats: dict[str, float]


def _to_number(value: object) -> float:
	if isinstance(value, (int, float)):
		return value

	text = str(value).strip().lstrip("+")

	if not text or text in {"-", "--"}:
		return 0

	if ":" in text:
		# Minutes occasionally arrive as MM:SS; the league scores whole minutes.
		text = text.split(":", 1)[0]

	try:
		return int(text)

	except ValueError:
		try:
			return float(text)

		except ValueError:
			return 0


def extract_games(scoreboard: dict) -> list[GameInfo]:
	"""Flatten an ESPN scoreboard payload into GameInfo rows."""  # noqa: DOC201
	games = []

	for event in scoreboard.get("events", ()):
		competition = (event.get("competitions") or [{}])[0]
		home_abbr = away_abbr = ""

		for competitor in competition.get("competitors", ()):
			abbr = (competitor.get("team") or {}).get("abbreviation", "")

			if competitor.get("homeAway") == "home":
				home_abbr = abbr

			else:
				away_abbr = abbr

		status = event.get("status") or {}
		status_type = status.get("type") or {}

		games.append(
			GameInfo(
				event_id=str(event["id"]),
				starts_at=datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00")),
				state=str(status_type.get("state") or "pre"),
				period=int(status.get("period") or 0),
				clock=str(status.get("displayClock") or ""),
				home_abbr=home_abbr,
				away_abbr=away_abbr,
			),
		)

	return games


def _winning_abbrs(summary: dict) -> set[str]:
	competitors = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("competitors", ())
	return {
		(competitor.get("team") or {}).get("abbreviation", "") for competitor in competitors if competitor.get("winner")
	}


def _box_stats(keys: list[str], raw_values: list[str]) -> dict[str, float]:
	stats: dict[str, float] = {}

	for key, raw in zip(keys, raw_values):
		if key in _PAIR_KEYS:
			made_key, attempted_key = _PAIR_KEYS[key]
			made, _, attempted = str(raw).partition("-")
			stats[made_key] = _to_number(made)
			stats[attempted_key] = _to_number(attempted)

		elif key in _SCALAR_KEYS:
			stats[_SCALAR_KEYS[key]] = _to_number(raw)

	return stats


def _pbp_counters(summary: dict, names_by_id: dict[str, str]) -> dict[str, dict[str, int]]:
	counters = {espn_id: {"TF": 0, "FLAGRANT": 0, "EJECTION": 0} for espn_id in names_by_id}
	names_longest_first = sorted(names_by_id.items(), key=lambda item: -len(item[1]))

	for play in summary.get("plays", ()):
		text = str(play.get("text") or "")
		lowered = text.lower()
		is_technical = "technical foul" in lowered and "technical free throw" not in lowered
		is_flagrant = "flagrant foul" in lowered
		is_ejection = "ejected" in lowered or "ejection" in lowered

		if not (is_technical or is_flagrant or is_ejection):
			continue

		espn_id = None

		for participant in play.get("participants") or ():
			candidate = str((participant.get("athlete") or {}).get("id") or "")

			if candidate in counters:
				espn_id = candidate
				break

		if espn_id is None:
			# Older payloads omit participants; fall back to the attributed name in the play text.
			for candidate_id, name in names_longest_first:
				if name and name in text:
					espn_id = candidate_id
					break

		if espn_id is None:
			continue

		if is_technical:
			counters[espn_id]["TF"] += 1

		if is_flagrant:
			counters[espn_id]["FLAGRANT"] += 1

		if is_ejection:
			counters[espn_id]["EJECTION"] += 1

	return counters


def extract_player_lines(summary: dict) -> list[PlayerLine]:
	"""Flatten an ESPN game summary into catalog-complete PlayerLine rows."""  # noqa: DOC201
	winning_abbrs = _winning_abbrs(summary)
	team_blobs = (summary.get("boxscore") or {}).get("players", ())
	entries = []
	names_by_id: dict[str, str] = {}

	for team_blob in team_blobs:
		team_abbr = (team_blob.get("team") or {}).get("abbreviation", "")
		statistics = team_blob.get("statistics") or [{}]
		keys = statistics[0].get("keys") or []

		for athlete_entry in statistics[0].get("athletes", ()):
			athlete = athlete_entry.get("athlete") or {}
			espn_id = str(athlete.get("id") or "")

			if not espn_id:
				continue

			names_by_id[espn_id] = str(athlete.get("displayName") or "")
			entries.append((espn_id, team_abbr, athlete_entry, keys))

	counters = _pbp_counters(summary, names_by_id)
	lines = []

	for espn_id, team_abbr, athlete_entry, keys in entries:
		raw_values = athlete_entry.get("stats") or []
		stats = _box_stats(keys, raw_values) if raw_values and not athlete_entry.get("didNotPlay") else {}
		stats["STARTED"] = 1 if athlete_entry.get("starter") else 0
		stats["WON"] = 1 if team_abbr in winning_abbrs else 0
		stats.update(counters[espn_id])
		full_stats = derive_fields(stats)

		for name in _SCALAR_KEYS.values():
			full_stats.setdefault(name, 0)

		for made_key, attempted_key in _PAIR_KEYS.values():
			full_stats.setdefault(made_key, 0)
			full_stats.setdefault(attempted_key, 0)

		lines.append(
			PlayerLine(espn_id=espn_id, display_name=names_by_id[espn_id], team_abbr=team_abbr, stats=full_stats)
		)

	return lines
```

Note: `derive_fields` runs before the `setdefault` backfill, so a DNP line gets `FG_MISS = 0 - 0 = 0` — re-run `derive_fields` is unnecessary because misses/DD/TD of an empty box are all zero either way.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_extract -v 2`
Expected: PASS (8 tests). If `test_starters_are_flagged` fails because the payload lacks `starter`, inspect the fixture (`python -c "..."`), adjust only the assertion to match reality (e.g. drop to `assertIn(sum(...), (0, 10))`) and note it in the commit body — `STARTED` degrading to 0 is spec-sanctioned.

- [ ] **Step 7: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/services/ scoring/tests/
git commit -m "feat: add ESPN client and catalog-complete stat extractors"
```

---

### Task 5: scoring periods + ingest + recompute

**Files:**
- Create: `scoring/services/periods.py`, `scoring/services/ingest.py`, `scoring/tests/test_ingest.py`

**Interfaces:**
- Consumes: `extract.GameInfo`, `extract.PlayerLine`, `engine.compile_formula`, `engine.CompiledFormula`, models from Task 3, `espn.ET`.
- Produces: `periods.generate_periods(first_day: date, last_day: date) -> int`, `periods.close_elapsed_periods(now: datetime) -> int`; `ingest.ESPN_ABBR_TO_NBA: dict[str, str]`, `ingest.get_active_rule() -> ScoringRule | None`, `ingest.get_active_compiled() -> CompiledFormula | None`, `ingest.upsert_game(info: GameInfo) -> NbaGame`, `ingest.upsert_lines(game: NbaGame, lines: list[PlayerLine], compiled: CompiledFormula | None) -> tuple[int, list[str]]` (updated count, unmatched display names), `ingest.recompute_all(rule: ScoringRule) -> int`.

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_ingest.py`:

```python
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core.models import NBATeam, Player
from scoring.engine import compile_formula
from scoring.models import NbaGame, PlayerGameLine, ScoringPeriod, ScoringRule
from scoring.services import ingest, periods
from scoring.services.extract import GameInfo, PlayerLine


def make_info(event_id: str = "401", state: str = "in", home: str = "SA", away: str = "NY") -> GameInfo:
	return GameInfo(
		event_id=event_id,
		starts_at=datetime(2026, 10, 20, 23, 0, tzinfo=dt_timezone.utc),
		state=state,
		period=2,
		clock="5:00",
		home_abbr=home,
		away_abbr=away,
	)


class PeriodsTests(TestCase):
	def test_generate_weekly_periods_and_close_elapsed(self) -> None:
		created = periods.generate_periods(date(2026, 10, 19), date(2026, 11, 1))
		self.assertEqual(created, 2)
		self.assertEqual(periods.generate_periods(date(2026, 10, 19), date(2026, 11, 1)), 0)
		closed = periods.close_elapsed_periods(timezone.make_aware(datetime(2026, 10, 27, 12, 0)))
		self.assertEqual(closed, 1)
		self.assertTrue(ScoringPeriod.objects.get(index=1).is_closed)


class UpsertGameTests(TestCase):
	def setUp(self) -> None:
		NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		NBATeam.objects.create(city="New York", name="Knicks", abbreviation="NYK")

	def test_espn_abbreviations_map_to_nba_teams(self) -> None:
		game = ingest.upsert_game(make_info())
		self.assertEqual(game.home.abbreviation, "SAS")
		self.assertEqual(game.away.abbreviation, "NYK")
		self.assertEqual(game.status, NbaGame.STATUS_LIVE)

	def test_settled_game_is_never_demoted(self) -> None:
		game = ingest.upsert_game(make_info(state="post"))
		game.status = NbaGame.STATUS_SETTLED
		game.save()
		game = ingest.upsert_game(make_info(state="post"))
		self.assertEqual(game.status, NbaGame.STATUS_SETTLED)

	def test_game_is_assigned_to_its_scoring_period(self) -> None:
		periods.generate_periods(date(2026, 10, 19), date(2026, 10, 25))
		game = ingest.upsert_game(make_info())
		self.assertIsNotNone(game.scoring_period)


class UpsertLinesTests(TestCase):
	def setUp(self) -> None:
		self.team = NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		self.player = Player.objects.create(
			first_name="Julian", last_name="Champagnie", primary_position="F", espn_id="111"
		)
		self.game = NbaGame.objects.create(
			espn_event_id="401", starts_at=timezone.now(), home=self.team, away=self.team
		)
		self.compiled = compile_formula("1*PTS + 2*STL")

	def test_upsert_computes_fpts_and_is_idempotent(self) -> None:
		lines = [
			PlayerLine(espn_id="111", display_name="Julian Champagnie", team_abbr="SA", stats={"PTS": 5, "STL": 4})
		]
		updated, unmatched = ingest.upsert_lines(self.game, lines, self.compiled)
		self.assertEqual((updated, unmatched), (1, []))
		self.assertEqual(PlayerGameLine.objects.get().fpts, Decimal("13.00"))
		updated, _ = ingest.upsert_lines(self.game, lines, self.compiled)
		self.assertEqual(updated, 1)
		self.assertEqual(PlayerGameLine.objects.count(), 1)

	def test_unknown_espn_id_is_reported_not_crashed(self) -> None:
		lines = [PlayerLine(espn_id="999", display_name="Un Known", team_abbr="SA", stats={"PTS": 5})]
		updated, unmatched = ingest.upsert_lines(self.game, lines, self.compiled)
		self.assertEqual((updated, unmatched), (0, ["Un Known"]))

	def test_recompute_all_applies_new_formula(self) -> None:
		lines = [
			PlayerLine(espn_id="111", display_name="Julian Champagnie", team_abbr="SA", stats={"PTS": 5, "STL": 4})
		]
		ingest.upsert_lines(self.game, lines, self.compiled)
		rule = ScoringRule.objects.create(name="new", formula_text="10*STL", is_active=True)
		count = ingest.recompute_all(rule)
		self.assertEqual(count, 1)
		self.assertEqual(PlayerGameLine.objects.get().fpts, Decimal("40.00"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_ingest -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.services.periods'`

- [ ] **Step 3: Implement `scoring/services/periods.py`**

```python
from datetime import date, datetime, time, timedelta

from scoring.models import ScoringPeriod
from scoring.services.espn import ET


def generate_periods(first_day: date, last_day: date) -> int:
	"""Create Mon-Sun ScoringPeriods covering [first_day, last_day]; returns how many were created."""  # noqa: DOC201
	monday = first_day - timedelta(days=first_day.weekday())
	existing = set(ScoringPeriod.objects.values_list("index", flat=True))
	created = 0
	index = max(existing, default=0)
	next_start = ScoringPeriod.objects.order_by("-index").first()
	cursor = monday if next_start is None else None

	if cursor is None:
		cursor = next_start.ends_at.astimezone(ET).date()

	while cursor <= last_day:
		index += 1
		starts_at = datetime.combine(cursor, time.min, tzinfo=ET)
		ends_at = starts_at + timedelta(days=7)
		ScoringPeriod.objects.create(index=index, starts_at=starts_at, ends_at=ends_at)
		created += 1
		cursor = cursor + timedelta(days=7)

	return created


def close_elapsed_periods(now: datetime) -> int:
	"""Close every still-open period that has fully elapsed; returns how many were closed."""  # noqa: DOC201
	return ScoringPeriod.objects.filter(is_closed=False, ends_at__lte=now).update(is_closed=True)
```

- [ ] **Step 4: Implement `scoring/services/ingest.py`**

```python
from decimal import Decimal

from django.db import transaction

from core.models import NBATeam, Player
from scoring.engine import CompiledFormula, compile_formula
from scoring.models import NbaGame, PlayerGameLine, ScoringPeriod, ScoringRule
from scoring.services.extract import GameInfo, PlayerLine

# ESPN abbreviations that differ from the NBA-standard ones used by core.NBATeam.
ESPN_ABBR_TO_NBA = {
	"GS": "GSW",
	"SA": "SAS",
	"NY": "NYK",
	"NO": "NOP",
	"UTAH": "UTA",
	"WSH": "WAS",
}

_STATE_TO_STATUS = {
	"pre": NbaGame.STATUS_SCHEDULED,
	"in": NbaGame.STATUS_LIVE,
	"post": NbaGame.STATUS_FINAL,
}

_RECOMPUTE_CHUNK = 500


def get_active_rule() -> ScoringRule | None:
	return ScoringRule.objects.filter(is_active=True).first()


def get_active_compiled() -> CompiledFormula | None:
	rule = get_active_rule()
	return compile_formula(rule.formula_text) if rule else None


def _nba_team(espn_abbr: str) -> NBATeam | None:
	return NBATeam.objects.filter(abbreviation=ESPN_ABBR_TO_NBA.get(espn_abbr, espn_abbr)).first()


def upsert_game(info: GameInfo) -> NbaGame:
	"""Create or refresh the NbaGame row for a scoreboard entry; never demotes a settled game."""  # noqa: DOC201
	game, _ = NbaGame.objects.get_or_create(
		espn_event_id=info.event_id,
		defaults={
			"starts_at": info.starts_at,
			"home": _nba_team(info.home_abbr),
			"away": _nba_team(info.away_abbr),
		},
	)
	game.starts_at = info.starts_at
	game.period = info.period
	game.clock = info.clock

	if game.status != NbaGame.STATUS_SETTLED:
		game.status = _STATE_TO_STATUS.get(info.state, game.status)

	if game.scoring_period is None:
		game.scoring_period = ScoringPeriod.for_datetime(info.starts_at)

	game.save()
	return game


def upsert_lines(game: NbaGame, lines: list[PlayerLine], compiled: CompiledFormula | None) -> tuple[int, list[str]]:
	"""Store raw stats (and fpts under the active rule) for every matched player."""  # noqa: DOC201
	players_by_espn_id = {player.espn_id: player for player in Player.objects.exclude(espn_id=None)}
	unmatched: list[str] = []
	updated = 0

	with transaction.atomic():
		for line in lines:
			player = players_by_espn_id.get(line.espn_id)

			if player is None:
				unmatched.append(line.display_name)
				continue

			fpts = compiled.evaluate(line.stats) if compiled else Decimal("0.00")
			PlayerGameLine.objects.update_or_create(
				player=player,
				game=game,
				defaults={"raw_stats": line.stats, "fpts": fpts},
			)
			updated += 1

	return updated, unmatched


def recompute_all(rule: ScoringRule) -> int:
	"""Re-derive fpts for every stored line under ``rule``; returns the number of lines updated."""  # noqa: DOC201
	compiled = compile_formula(rule.formula_text)
	updated = 0
	batch: list[PlayerGameLine] = []

	with transaction.atomic():
		for line in PlayerGameLine.objects.all().iterator():
			line.fpts = compiled.evaluate(line.raw_stats)
			batch.append(line)

			if len(batch) >= _RECOMPUTE_CHUNK:
				PlayerGameLine.objects.bulk_update(batch, ("fpts",))
				updated += len(batch)
				batch = []

		if batch:
			PlayerGameLine.objects.bulk_update(batch, ("fpts",))
			updated += len(batch)

	return updated
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_ingest -v 2`
Expected: PASS (8 tests)

- [ ] **Step 6: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/services/ scoring/tests/test_ingest.py
git commit -m "feat: add scoring periods, line ingest, and full recompute"
```

---

### Task 6: settle logic + live worker command

**Files:**
- Create: `scoring/services/settle.py`, `scoring/management/__init__.py` (empty), `scoring/management/commands/__init__.py` (empty), `scoring/management/commands/live_scoring_worker.py`, `scoring/tests/test_worker.py`

**Interfaces:**
- Consumes: `espn.*`, `extract.*`, `ingest.*`, `periods.close_elapsed_periods`, `corrections.sweep` (Task 7 — stub import guarded, see Step 4), `settle.box_hash`.
- Produces: `settle.box_hash(lines: Iterable[PlayerLine]) -> str`; management command `live_scoring_worker` with options `--once`, `--poll-live` (default 25), `--poll-final` (default 120), `--sweep-hour` (default 10).

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_worker.py`:

```python
import json
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from core.models import NBATeam, Player
from scoring.models import NbaGame, PlayerGameLine
from scoring.services.extract import PlayerLine
from scoring.services.settle import box_hash

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
	return json.loads((FIXTURES / name).read_text())


class BoxHashTests(TestCase):
	def test_hash_is_order_independent_and_content_sensitive(self) -> None:
		line_a = PlayerLine(espn_id="1", display_name="A", team_abbr="SA", stats={"PTS": 5})
		line_b = PlayerLine(espn_id="2", display_name="B", team_abbr="NY", stats={"PTS": 7})
		self.assertEqual(box_hash([line_a, line_b]), box_hash([line_b, line_a]))
		changed = PlayerLine(espn_id="2", display_name="B", team_abbr="NY", stats={"PTS": 8})
		self.assertNotEqual(box_hash([line_a, line_b]), box_hash([line_a, changed]))


def _empty_summary() -> dict:
	return {"boxscore": {"players": []}, "plays": [], "header": {"competitions": [{"competitors": []}]}}


@mock.patch("scoring.management.commands.live_scoring_worker.corrections", create=True)
@mock.patch("scoring.services.espn.save_snapshot", lambda payload, event_id: None)
class WorkerOnceTests(TestCase):
	def setUp(self) -> None:
		NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		NBATeam.objects.create(city="New York", name="Knicks", abbreviation="NYK")
		# One real player from the fixture so lines get stored (espn id read from the fixture itself).
		summary = load_fixture("espn_summary_401859966.json")
		first_team = summary["boxscore"]["players"][0]
		athlete = first_team["statistics"][0]["athletes"][0]["athlete"]
		self.espn_id = str(athlete["id"])
		first, _, last = str(athlete["displayName"]).partition(" ")
		Player.objects.create(first_name=first, last_name=last or first, primary_position="F", espn_id=self.espn_id)

	def _run_once(self) -> None:
		scoreboard = load_fixture("espn_scoreboard_finals_2026.json")
		summary = load_fixture("espn_summary_401859966.json")

		def fake_summary(event_id: str) -> dict:
			return summary if event_id == "401859966" else _empty_summary()

		with (
			mock.patch("scoring.services.espn.fetch_scoreboard", return_value=scoreboard),
			mock.patch("scoring.services.espn.fetch_summary", side_effect=fake_summary),
		):
			call_command("live_scoring_worker", "--once")

	def test_two_stable_passes_settle_the_game(self, _corrections: mock.MagicMock) -> None:
		self._run_once()
		game = NbaGame.objects.get(espn_event_id="401859966")
		self.assertEqual(game.status, NbaGame.STATUS_FINAL)
		self.assertTrue(game.settle_hash)
		self.assertFalse(game.lines.filter(is_final=True).exists())
		self.assertTrue(PlayerGameLine.objects.filter(player__espn_id=self.espn_id).exists())

		self._run_once()
		game.refresh_from_db()
		self.assertEqual(game.status, NbaGame.STATUS_SETTLED)
		self.assertTrue(game.lines.filter(is_final=True).exists())

	def test_no_games_tick_is_clean(self, _corrections: mock.MagicMock) -> None:
		with mock.patch("scoring.services.espn.fetch_scoreboard", return_value={"events": []}):
			call_command("live_scoring_worker", "--once")
		self.assertEqual(NbaGame.objects.count(), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_worker -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.services.settle'`

- [ ] **Step 3: Implement `scoring/services/settle.py`**

```python
import hashlib
import json
from collections.abc import Iterable

from scoring.services.extract import PlayerLine


def box_hash(lines: Iterable[PlayerLine]) -> str:
	"""Stable content hash of a game's box, used to detect that ESPN stopped revising it."""  # noqa: DOC201
	payload = {line.espn_id: line.stats for line in lines}
	return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```

- [ ] **Step 4: Implement the worker command**

`scoring/management/commands/live_scoring_worker.py`:

```python
import logging
import time
from datetime import timedelta
from typing import Any

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from scoring.models import NbaGame
from scoring.services import corrections, espn, extract, ingest, periods, settle

logger = logging.getLogger(__name__)

_MIN_SLEEP_SECONDS = 30
_MAX_SLEEP_SECONDS = 3600
_PREGAME_LEAD_SECONDS = 300


class Command(BaseCommand):
	"""Poll ESPN for live stats, settle finished games fast, and run the daily corrections sweep."""

	help = "Poll ESPN for live NBA stats, settle finished games, run daily corrections sweep"

	def add_arguments(self, parser) -> None:  # noqa: ANN001, D102, PLR6301
		parser.add_argument("--once", action="store_true", help="Run a single tick and exit (for tests/cron)")
		parser.add_argument("--poll-live", type=int, default=25, help="Seconds between polls while games are live")
		parser.add_argument("--poll-final", type=int, default=120, help="Seconds between polls while settling finals")
		parser.add_argument("--sweep-hour", type=int, default=10, help="Local hour after which the daily sweep runs")

	def handle(self, *_: Any, **options: Any) -> None:  # noqa: D102
		self._last_sweep_date = None

		while True:
			try:
				sleep_seconds = self.tick(
					poll_live=int(options["poll_live"]),
					poll_final=int(options["poll_final"]),
					sweep_hour=int(options["sweep_hour"]),
				)

			except Exception:
				logger.exception("Worker tick failed")
				sleep_seconds = 60

			if options["once"]:
				return

			time.sleep(sleep_seconds)

	def tick(self, poll_live: int, poll_final: int, sweep_hour: int) -> float:
		"""Run one poll cycle and return how long to sleep before the next."""  # noqa: DOC201
		today = espn.et_today()
		infos = []

		for day in (today - timedelta(days=1), today):
			try:
				infos.extend(extract.extract_games(espn.fetch_scoreboard(day)))

			except requests.RequestException:
				logger.exception("Scoreboard fetch failed for %s", day)

		# The two scoreboards can list the same game (late tips); poll each game at most once per tick.
		infos = list({info.event_id: info for info in infos}.values())
		compiled = ingest.get_active_compiled()
		tracked = []

		for info in infos:
			game = ingest.upsert_game(info)

			if game.status in (NbaGame.STATUS_LIVE, NbaGame.STATUS_FINAL):
				tracked.append(game)

		for game in tracked:
			try:
				self.poll_game(game, compiled)

			except requests.RequestException:
				logger.exception("Summary fetch failed for %s", game.espn_event_id)

		self.maybe_sweep(sweep_hour)
		periods.close_elapsed_periods(timezone.now())

		if any(game.status == NbaGame.STATUS_LIVE for game in tracked):
			return poll_live

		if any(game.status == NbaGame.STATUS_FINAL for game in tracked):
			return poll_final

		return self.sleep_until_next_start(infos)

	def poll_game(self, game: NbaGame, compiled) -> None:  # noqa: ANN001
		summary = espn.fetch_summary(game.espn_event_id)
		espn.save_snapshot(summary, game.espn_event_id)
		lines = extract.extract_player_lines(summary)
		updated, unmatched = ingest.upsert_lines(game, lines, compiled)

		if unmatched:
			logger.warning("%s: %d unmatched players: %s", game.espn_event_id, len(unmatched), ", ".join(unmatched[:5]))

		self.stdout.write(f"{timezone.now():%H:%M:%S} {game.espn_event_id} [{game.status}] {updated} lines")

		if game.status == NbaGame.STATUS_FINAL:
			new_hash = settle.box_hash(lines)

			if new_hash == game.settle_hash:
				game.status = NbaGame.STATUS_SETTLED
				game.lines.update(is_final=True)
				self.stdout.write(self.style.SUCCESS(f"{game.espn_event_id} settled"))

			else:
				game.settle_hash = new_hash

			game.save()

	def maybe_sweep(self, sweep_hour: int) -> None:
		now_local = timezone.localtime()

		if now_local.hour >= sweep_hour and self._last_sweep_date != now_local.date():
			corrections.sweep()
			self._last_sweep_date = now_local.date()

	def sleep_until_next_start(self, infos: list[extract.GameInfo]) -> float:
		"""Idle until shortly before the next scheduled tip-off."""  # noqa: DOC201
		now = timezone.now()
		upcoming = [info.starts_at for info in infos if info.state == "pre" and info.starts_at > now]

		if not upcoming:
			return _MAX_SLEEP_SECONDS

		wait = (min(upcoming) - now).total_seconds() - _PREGAME_LEAD_SECONDS
		return max(_MIN_SLEEP_SECONDS, min(wait, _MAX_SLEEP_SECONDS))
```

`corrections` does not exist until Task 7. Create a placeholder module now so the import works:

`scoring/services/corrections.py`:

```python
def sweep(days_back: int = 3) -> dict:
	"""Placeholder until the corrections sweep lands (Task 7)."""  # noqa: DOC201
	return {"games": 0, "corrections": 0, "applied": 0}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_worker -v 2`
Expected: PASS (3 tests)

- [ ] **Step 6: Full suite, format, commit**

```bash
.venv/bin/python manage.py test scoring -v 1
ruff check --fix && ruff format
git add scoring/
git commit -m "feat: add live scoring worker with fast end-of-game settlement"
```

---

### Task 7: T+1 stat-corrections sweep

**Files:**
- Modify: `scoring/services/corrections.py` (replace the Task 6 placeholder)
- Create: `scoring/tests/test_corrections.py`

**Interfaces:**
- Consumes: `espn.fetch_summary`, `espn.save_snapshot`, `extract.extract_player_lines`, `ingest.get_active_compiled`, models, `core.models.Notification`.
- Produces: `corrections.sweep(days_back: int = 3) -> dict` with keys `games`, `corrections`, `applied`; `corrections._owner_of(line) -> User | None` (module-private but patched in tests).

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_corrections.py`:

```python
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import NBATeam, Notification, Player
from scoring.models import NbaGame, PlayerGameLine, ScoringPeriod, ScoringRule, StatCorrection
from scoring.services import corrections
from scoring.services.extract import PlayerLine


class SweepTests(TestCase):
	def setUp(self) -> None:
		now = timezone.now()
		self.period = ScoringPeriod.objects.create(
			index=1, starts_at=now - timedelta(days=3), ends_at=now + timedelta(days=4)
		)
		self.team = NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		self.player = Player.objects.create(
			first_name="Julian", last_name="Champagnie", primary_position="F", espn_id="111"
		)
		self.game = NbaGame.objects.create(
			espn_event_id="401",
			starts_at=now - timedelta(days=1),
			home=self.team,
			away=self.team,
			status=NbaGame.STATUS_SETTLED,
			scoring_period=self.period,
		)
		ScoringRule.objects.create(name="league", formula_text="1*PTS + 1*AST", is_active=True)
		self.line = PlayerGameLine.objects.create(
			player=self.player,
			game=self.game,
			raw_stats={"PTS": 20, "AST": 5},
			fpts=Decimal("25.00"),
			is_final=True,
		)

	def _sweep_with(self, new_stats: dict) -> dict:
		new_lines = [PlayerLine(espn_id="111", display_name="Julian Champagnie", team_abbr="SA", stats=new_stats)]
		with (
			mock.patch.object(corrections.espn, "fetch_summary", return_value={}),
			mock.patch.object(corrections.espn, "save_snapshot", return_value=None),
			mock.patch.object(corrections.extract, "extract_player_lines", return_value=new_lines),
		):
			return corrections.sweep()

	def test_open_period_applies_correction_and_recomputes(self) -> None:
		user = get_user_model().objects.create_user(username="owner", password="x")
		with mock.patch.object(corrections, "_owner_of", return_value=user):
			result = self._sweep_with({"PTS": 20, "AST": 6})
		self.assertEqual(result["applied"], 1)
		self.line.refresh_from_db()
		self.assertEqual(self.line.raw_stats["AST"], 6)
		self.assertEqual(self.line.fpts, Decimal("26.00"))
		correction = StatCorrection.objects.get()
		self.assertTrue(correction.applied)
		self.assertEqual((correction.field, correction.old_value, correction.new_value), ("AST", 5, 6))
		self.assertEqual(Notification.objects.filter(user=user).count(), 1)

	def test_closed_period_records_but_never_applies(self) -> None:
		self.period.is_closed = True
		self.period.save()
		result = self._sweep_with({"PTS": 20, "AST": 6})
		self.assertEqual(result["applied"], 0)
		self.assertEqual(result["corrections"], 1)
		self.line.refresh_from_db()
		self.assertEqual(self.line.raw_stats["AST"], 5)
		self.assertEqual(self.line.fpts, Decimal("25.00"))
		self.assertFalse(StatCorrection.objects.get().applied)
		self.assertEqual(Notification.objects.count(), 0)

	def test_identical_stats_are_a_no_op(self) -> None:
		result = self._sweep_with({"PTS": 20, "AST": 5})
		self.assertEqual(result["corrections"], 0)
		self.assertEqual(StatCorrection.objects.count(), 0)

	def test_unowned_player_correction_applies_without_notification(self) -> None:
		result = self._sweep_with({"PTS": 21, "AST": 5})
		self.assertEqual(result["applied"], 1)
		self.assertEqual(Notification.objects.count(), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_corrections -v 2`
Expected: FAIL — sweep returns zeros (placeholder), assertions on corrections fail.

- [ ] **Step 3: Implement `scoring/services/corrections.py` (replace placeholder)**

```python
import logging
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from core.models import Notification
from scoring.models import NbaGame, PlayerGameLine, StatCorrection
from scoring.services import espn, extract, ingest

logger = logging.getLogger(__name__)


def _owner_of(line: PlayerGameLine):  # noqa: ANN202
	try:
		return line.player.contract.team.owner

	except (ObjectDoesNotExist, AttributeError):
		return None


def sweep(days_back: int = 3) -> dict:
	"""Re-fetch recently settled games and reconcile official stat corrections.

	Open scoring period: apply the correction, recompute fpts, notify the owner.
	Closed period: record the diff only — settled weeks never restate.
	"""  # noqa: DOC201
	cutoff = timezone.now() - timedelta(days=days_back)
	compiled = ingest.get_active_compiled()
	result = {"games": 0, "corrections": 0, "applied": 0}

	for game in NbaGame.objects.filter(status=NbaGame.STATUS_SETTLED, starts_at__gte=cutoff).select_related(
		"scoring_period"
	):
		summary = espn.fetch_summary(game.espn_event_id)
		espn.save_snapshot(summary, game.espn_event_id)
		fresh = {line.espn_id: line for line in extract.extract_player_lines(summary)}
		result["games"] += 1
		period_open = game.scoring_period is None or not game.scoring_period.is_closed

		for stored in game.lines.select_related("player"):
			fresh_line = fresh.get(stored.player.espn_id)

			if fresh_line is None:
				continue

			diffs = [
				(field, stored.raw_stats.get(field, 0), value)
				for field, value in fresh_line.stats.items()
				if stored.raw_stats.get(field, 0) != value
			]

			if not diffs:
				continue

			for field, old_value, new_value in diffs:
				StatCorrection.objects.create(
					line=stored,
					field=field,
					old_value=old_value,
					new_value=new_value,
					applied=period_open,
				)
				result["corrections"] += 1

			if not period_open:
				continue

			old_fpts = stored.fpts
			stored.raw_stats = fresh_line.stats

			if compiled:
				stored.fpts = compiled.evaluate(fresh_line.stats)

			stored.save()
			result["applied"] += len(diffs)
			owner = _owner_of(stored)

			if owner is not None:
				delta = stored.fpts - old_fpts
				Notification.objects.create(
					user=owner,
					message=f"Stat correction: {stored.player} revised, fantasy points {old_fpts} -> {stored.fpts} ({delta:+})",
					level="info",
					priority=1,
				)

	return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_corrections -v 2`
Expected: PASS (4 tests). The Task 6 worker tests must still pass (`manage.py test scoring.tests.test_worker`).

- [ ] **Step 5: Format and commit**

```bash
ruff check --fix && ruff format
git add scoring/services/corrections.py scoring/tests/test_corrections.py
git commit -m "feat: add T+1 stat-corrections sweep with period-close freeze"
```

---

### Task 8: REST API (fields, rules CRUD, preview, activate/recompute, games)

**Files:**
- Create: `scoring/permissions.py`, `scoring/serializers.py`, `scoring/views.py`, `scoring/urls.py`, `scoring/tests/test_api.py`
- Modify: `ftt/urls.py`

**Interfaces:**
- Consumes: `FIELD_CATALOG`, `engine.compile_formula`/`FormulaError`, `ingest.recompute_all`, models.
- Produces (consumed by the frontend in Tasks 10-11):
  - `GET /api/scoring/fields/` → `[{name, label, description, example, source}]` (authenticated)
  - `GET /api/scoring/games/?date=YYYY-MM-DD` → `[{espn_event_id, starts_at, status, label}]` (superuser)
  - `GET|POST /api/scoring/rules/`, `GET|PUT|PATCH|DELETE /api/scoring/rules/{id}/` (superuser; `is_active` is read-only here)
  - `POST /api/scoring/rules/preview/` `{formula_text, espn_event_id}` → `{players: [{player_name, espn_id, stats, fpts, active_fpts, delta}]}` | `400 {error, position, suggestion}` | `404 {error}`
  - `POST /api/scoring/rules/{id}/activate/` → `{is_active: true, updated: n}` (deactivates others, recomputes)
  - `POST /api/scoring/rules/{id}/recompute/` → `{updated: n}`
- Design note: saving an edit does NOT auto-recompute server-side; the builder UI always follows a save with `activate` (which recomputes) or `recompute`. This keeps counts in one place and avoids double recomputes.

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_api.py`:

```python
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import NBATeam, Player
from scoring.models import NbaGame, PlayerGameLine, ScoringRule


class ScoringApiTests(TestCase):
	def setUp(self) -> None:
		user_model = get_user_model()
		self.superuser = user_model.objects.create_superuser(username="boss", password="x")
		self.mortal = user_model.objects.create_user(username="pleb", password="x")
		self.client_api = APIClient()
		team = NBATeam.objects.create(city="San Antonio", name="Spurs", abbreviation="SAS")
		self.player = Player.objects.create(
			first_name="Julian", last_name="Champagnie", primary_position="F", espn_id="111"
		)
		self.game = NbaGame.objects.create(espn_event_id="401", starts_at=timezone.now(), home=team, away=team)
		self.rule = ScoringRule.objects.create(name="league", formula_text="1*PTS", is_active=True)
		PlayerGameLine.objects.create(
			player=self.player, game=self.game, raw_stats={"PTS": 20, "STL": 4}, fpts=Decimal("20.00")
		)

	def test_fields_requires_auth_and_lists_catalog(self) -> None:
		self.assertEqual(self.client_api.get("/api/scoring/fields/").status_code, 401)
		self.client_api.force_authenticate(self.mortal)
		response = self.client_api.get("/api/scoring/fields/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.json()), 27)

	def test_rules_are_superuser_only(self) -> None:
		self.client_api.force_authenticate(self.mortal)
		self.assertEqual(self.client_api.get("/api/scoring/rules/").status_code, 403)
		self.assertEqual(
			self.client_api.post("/api/scoring/rules/", {"name": "x", "formula_text": "1*PTS"}).status_code, 403
		)

	def test_create_rule_validates_formula(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		bad = self.client_api.post("/api/scoring/rules/", {"name": "bad", "formula_text": "1*NOPE"})
		self.assertEqual(bad.status_code, 400)
		good = self.client_api.post("/api/scoring/rules/", {"name": "good", "formula_text": "2*PTS"})
		self.assertEqual(good.status_code, 201)

	def test_preview_returns_rows_with_delta(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		response = self.client_api.post(
			"/api/scoring/rules/preview/",
			{"formula_text": "1*PTS + 2*STL", "espn_event_id": "401"},
			format="json",
		)
		self.assertEqual(response.status_code, 200)
		row = response.json()["players"][0]
		self.assertEqual(row["player_name"], "Julian Champagnie")
		self.assertEqual(row["fpts"], "28.00")
		self.assertEqual(row["active_fpts"], "20.00")
		self.assertEqual(row["delta"], "8.00")

	def test_preview_reports_formula_errors_with_position_and_suggestion(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		response = self.client_api.post(
			"/api/scoring/rules/preview/",
			{"formula_text": "1*FTMISS", "espn_event_id": "401"},
			format="json",
		)
		self.assertEqual(response.status_code, 400)
		body = response.json()
		self.assertIn("FTMISS", body["error"])
		self.assertEqual(body["suggestion"], "FT_MISS")
		self.assertIsNotNone(body["position"])

	def test_preview_unknown_game_is_404(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		response = self.client_api.post(
			"/api/scoring/rules/preview/",
			{"formula_text": "1*PTS", "espn_event_id": "999"},
			format="json",
		)
		self.assertEqual(response.status_code, 404)

	def test_activate_is_exclusive_and_recomputes(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		other = ScoringRule.objects.create(name="other", formula_text="2*PTS")
		response = self.client_api.post(f"/api/scoring/rules/{other.pk}/activate/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["updated"], 1)
		self.rule.refresh_from_db()
		other.refresh_from_db()
		self.assertFalse(self.rule.is_active)
		self.assertTrue(other.is_active)
		line = PlayerGameLine.objects.get()
		self.assertEqual(line.fpts, Decimal("40.00"))

	def test_recompute_returns_count(self) -> None:
		self.client_api.force_authenticate(self.superuser)
		response = self.client_api.post(f"/api/scoring/rules/{self.rule.pk}/recompute/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["updated"], 1)

	def test_games_filterable_by_date_superuser_only(self) -> None:
		self.client_api.force_authenticate(self.mortal)
		self.assertEqual(self.client_api.get("/api/scoring/games/").status_code, 403)
		self.client_api.force_authenticate(self.superuser)
		day = timezone.localtime().date().isoformat()
		response = self.client_api.get(f"/api/scoring/games/?date={day}")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()[0]["espn_event_id"], "401")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_api -v 2`
Expected: FAIL — 404s everywhere (`/api/scoring/...` not routed yet).

- [ ] **Step 3: Implement permission, serializers, views, urls**

`scoring/permissions.py`:

```python
from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
	"""Allow only Django superusers (league commissioners)."""

	def has_permission(self, request, view) -> bool:  # noqa: ANN001, D102
		return bool(request.user and request.user.is_authenticated and request.user.is_superuser)
```

`scoring/serializers.py`:

```python
from rest_framework import serializers

from scoring.engine import FormulaError, validate_formula
from scoring.models import NbaGame, ScoringRule


class ScoringRuleSerializer(serializers.ModelSerializer):
	class Meta:
		model = ScoringRule
		fields = ("id", "name", "formula_text", "weights_json", "is_active", "updated_at")
		read_only_fields = ("id", "is_active", "updated_at")

	def validate_formula_text(self, value: str) -> str:  # noqa: D102
		try:
			validate_formula(value)

		except FormulaError as exc:
			raise serializers.ValidationError(exc.message) from exc

		return value


class PreviewRequestSerializer(serializers.Serializer):
	formula_text = serializers.CharField()
	espn_event_id = serializers.CharField()


class NbaGameSerializer(serializers.ModelSerializer):
	label = serializers.SerializerMethodField()

	class Meta:
		model = NbaGame
		fields = ("espn_event_id", "starts_at", "status", "label")

	def get_label(self, obj: NbaGame) -> str:  # noqa: D102, PLR6301
		away = obj.away.abbreviation if obj.away else "?"
		home = obj.home.abbreviation if obj.home else "?"
		return f"{away} @ {home}"
```

`scoring/views.py`:

```python
from django.db import transaction
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from scoring.engine import FormulaError, compile_formula
from scoring.fields import FIELD_CATALOG
from scoring.models import NbaGame, ScoringRule
from scoring.permissions import IsSuperUser
from scoring.serializers import NbaGameSerializer, PreviewRequestSerializer, ScoringRuleSerializer
from scoring.services import ingest


class ScoringFieldsView(APIView):
	permission_classes = (IsAuthenticated,)

	@extend_schema(tags=["Scoring"], summary="List every stat field available to scoring formulas")
	def get(self, request) -> Response:  # noqa: ANN001, ARG002, D102, PLR6301
		return Response([spec._asdict() for spec in FIELD_CATALOG.values()])


class ScoringGamesView(APIView):
	permission_classes = (IsSuperUser,)

	@extend_schema(tags=["Scoring"], summary="List ingested NBA games, optionally by local date")
	def get(self, request) -> Response:  # noqa: ANN001, D102, PLR6301
		queryset = NbaGame.objects.select_related("home", "away").order_by("-starts_at")
		day = parse_date(request.query_params.get("date", ""))

		if day:
			queryset = queryset.filter(starts_at__date=day)

		return Response(NbaGameSerializer(queryset[:50], many=True).data)


@extend_schema(tags=["Scoring"])
class ScoringRuleViewSet(viewsets.ModelViewSet):
	queryset = ScoringRule.objects.order_by("-updated_at")
	serializer_class = ScoringRuleSerializer
	permission_classes = (IsSuperUser,)

	def perform_create(self, serializer) -> None:  # noqa: ANN001, D102
		serializer.save(updated_by=self.request.user)

	def perform_update(self, serializer) -> None:  # noqa: ANN001, D102
		serializer.save(updated_by=self.request.user)

	@action(detail=False, methods=["post"])
	def preview(self, request) -> Response:  # noqa: ANN001, D102
		request_serializer = PreviewRequestSerializer(data=request.data)
		request_serializer.is_valid(raise_exception=True)

		try:
			compiled = compile_formula(request_serializer.validated_data["formula_text"])

		except FormulaError as exc:
			return Response({"error": exc.message, "position": exc.position, "suggestion": exc.suggestion}, status=400)

		game = NbaGame.objects.filter(espn_event_id=request_serializer.validated_data["espn_event_id"]).first()

		if game is None:
			return Response(
				{"error": "Game not ingested yet. Run backfill_season or wait for the live worker."}, status=404
			)

		players = []

		for line in game.lines.select_related("player"):
			fpts = compiled.evaluate(line.raw_stats)
			players.append({
				"player_name": str(line.player),
				"espn_id": line.player.espn_id,
				"stats": line.raw_stats,
				"fpts": str(fpts),
				"active_fpts": str(line.fpts),
				"delta": str(fpts - line.fpts),
			})

		players.sort(key=lambda row: float(row["fpts"]), reverse=True)
		return Response({"players": players})

	@action(detail=True, methods=["post"])
	def activate(self, request, pk=None) -> Response:  # noqa: ANN001, ARG002, D102
		rule = self.get_object()

		with transaction.atomic():
			ScoringRule.objects.filter(is_active=True).exclude(pk=rule.pk).update(is_active=False)
			rule.is_active = True
			rule.save()

		return Response({"is_active": True, "updated": ingest.recompute_all(rule)})

	@action(detail=True, methods=["post"])
	def recompute(self, request, pk=None) -> Response:  # noqa: ANN001, ARG002, D102
		return Response({"updated": ingest.recompute_all(self.get_object())})
```

`scoring/urls.py`:

```python
from django.urls import path
from rest_framework.routers import SimpleRouter

from scoring import views

router = SimpleRouter()
router.register("rules", views.ScoringRuleViewSet, basename="scoring-rule")

urlpatterns = [
	path("fields/", views.ScoringFieldsView.as_view(), name="scoring-fields"),
	path("games/", views.ScoringGamesView.as_view(), name="scoring-games"),
	*router.urls,
]
```

`ftt/urls.py` — add after the `trade.urls` include:

```python
(path("api/scoring/", include("scoring.urls")),)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python manage.py test scoring.tests.test_api -v 2`
Expected: PASS (9 tests). Note: unauthenticated may return 401 or 403 depending on DRF defaults — this project uses JWT + `IsAuthenticated`, which yields 401 for anonymous; if `test_fields_requires_auth_and_lists_catalog` sees 403, change the assertion to `assertIn(response.status_code, (401, 403))` — both mean "locked out".

- [ ] **Step 5: Full suite, format, commit**

```bash
.venv/bin/python manage.py test scoring -v 1
ruff check --fix && ruff format
git add scoring/ ftt/urls.py
git commit -m "feat: add scoring API (fields, rules, preview, activate, recompute)"
```

---

### Task 9: crosswalk, backfill, and parity commands

**Files:**
- Create: `scoring/services/crosswalk.py`, `scoring/management/commands/backfill_season.py`, `scoring/management/commands/parity_check.py`, `scoring/tests/test_crosswalk.py`

**Interfaces:**
- Consumes: `espn.*`, `extract.*`, `ingest.*`, `periods.generate_periods`, `core.models.Player`.
- Produces: `crosswalk.normalize_name(name: str) -> str`, `crosswalk.map_espn_ids(names_by_espn_id: dict[str, str]) -> dict` (keys `mapped: int`, `unmatched: list[str]`, `ambiguous: list[str]`); commands `backfill_season --start YYYY-MM-DD --end YYYY-MM-DD [--sleep 0.5]` and `parity_check <csv_path> [--tolerance 1.0]`.

- [ ] **Step 1: Write the failing tests**

`scoring/tests/test_crosswalk.py`:

```python
from django.test import TestCase

from core.models import Player
from scoring.services.crosswalk import map_espn_ids, normalize_name


class NormalizeNameTests(TestCase):
	def test_strips_accents_suffixes_and_punctuation(self) -> None:
		self.assertEqual(normalize_name("Luka Dončić"), "luka doncic")
		self.assertEqual(normalize_name("Jaren Jackson Jr."), "jaren jackson")
		self.assertEqual(normalize_name("Shaquille O'Neal"), "shaquille oneal")
		self.assertEqual(normalize_name("Shai Gilgeous-Alexander"), "shai gilgeous alexander")
		self.assertEqual(normalize_name("Wendell Carter III"), "wendell carter")


class MapEspnIdsTests(TestCase):
	def test_unique_match_sets_espn_id(self) -> None:
		player = Player.objects.create(first_name="Luka", last_name="Dončić", primary_position="G")
		report = map_espn_ids({"3945274": "Luka Doncic"})
		player.refresh_from_db()
		self.assertEqual(player.espn_id, "3945274")
		self.assertEqual(report["mapped"], 1)

	def test_ambiguous_names_are_reported_not_guessed(self) -> None:
		Player.objects.create(first_name="John", last_name="Smith", primary_position="G")
		Player.objects.create(first_name="John", last_name="Smith", primary_position="F", slug="john-smith-2")
		report = map_espn_ids({"1": "John Smith"})
		self.assertEqual(report["mapped"], 0)
		self.assertEqual(report["ambiguous"], ["John Smith"])
		self.assertFalse(Player.objects.exclude(espn_id=None).exists())

	def test_unknown_names_are_reported(self) -> None:
		report = map_espn_ids({"2": "Nobody Wemayo"})
		self.assertEqual(report["unmatched"], ["Nobody Wemayo"])

	def test_already_mapped_ids_are_skipped(self) -> None:
		Player.objects.create(first_name="Luka", last_name="Dončić", primary_position="G", espn_id="3945274")
		Player.objects.create(first_name="Luka", last_name="Doncic Two", primary_position="G")
		report = map_espn_ids({"3945274": "Luka Doncic"})
		self.assertEqual(report["mapped"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python manage.py test scoring.tests.test_crosswalk -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'scoring.services.crosswalk'`

- [ ] **Step 3: Implement `scoring/services/crosswalk.py`**

```python
import unidecode

from core.models import Player

_SUFFIXES = (" jr.", " jr", " sr.", " sr", " iv", " iii", " ii")


def normalize_name(name: str) -> str:
	"""Normalize a player name for matching across ESPN and league spellings."""  # noqa: DOC201
	text = unidecode.unidecode(name).lower().strip()

	for suffix in _SUFFIXES:
		text = text.removesuffix(suffix)

	return text.replace("'", "").replace(".", "").replace("-", " ").strip()


def map_espn_ids(names_by_espn_id: dict[str, str]) -> dict:
	"""Set Player.espn_id by normalized full-name match.

	Only unambiguous matches are written; everything else lands in the report
	for manual fixing via Django admin.
	"""  # noqa: DOC201
	players_by_name: dict[str, list[Player]] = {}

	for player in Player.objects.filter(espn_id=None):
		players_by_name.setdefault(normalize_name(f"{player.first_name} {player.last_name}"), []).append(player)

	taken = set(Player.objects.exclude(espn_id=None).values_list("espn_id", flat=True))
	report: dict = {"mapped": 0, "unmatched": [], "ambiguous": []}

	for espn_id, display_name in names_by_espn_id.items():
		if espn_id in taken:
			continue

		candidates = players_by_name.get(normalize_name(display_name), [])

		if len(candidates) == 1:
			candidates[0].espn_id = espn_id
			candidates[0].save()
			taken.add(espn_id)
			report["mapped"] += 1

		elif candidates:
			report["ambiguous"].append(display_name)

		else:
			report["unmatched"].append(display_name)

	return report
```

- [ ] **Step 4: Run crosswalk tests**

Run: `.venv/bin/python manage.py test scoring.tests.test_crosswalk -v 2`
Expected: PASS (6 tests)

- [ ] **Step 5: Implement the backfill command**

`scoring/management/commands/backfill_season.py`:

```python
import time
from datetime import date, timedelta
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError

from scoring.models import NbaGame
from scoring.services import crosswalk, espn, extract, ingest, periods


class Command(BaseCommand):
	"""Backfill finished NBA games and player lines from ESPN for a date range."""

	help = "Backfill NBA games and player lines from ESPN for a date range"

	def add_arguments(self, parser) -> None:  # noqa: ANN001, D102, PLR6301
		parser.add_argument("--start", required=True, help="First day, YYYY-MM-DD (ET)")
		parser.add_argument("--end", required=True, help="Last day, YYYY-MM-DD (ET)")
		parser.add_argument("--sleep", type=float, default=0.5, help="Seconds between ESPN requests")

	def handle(self, *_: Any, **options: Any) -> None:  # noqa: D102
		try:
			start = date.fromisoformat(options["start"])
			end = date.fromisoformat(options["end"])

		except ValueError as exc:
			raise CommandError(f"Bad date: {exc}") from exc

		periods.generate_periods(start, end)
		compiled = ingest.get_active_compiled()
		games_done = 0
		lines_done = 0
		unmatched: set[str] = set()
		day = start

		while day <= end:
			try:
				infos = extract.extract_games(espn.fetch_scoreboard(day))

			except requests.RequestException as exc:
				self.stderr.write(f"{day}: scoreboard failed ({exc}); skipping day")
				day += timedelta(days=1)
				continue

			for info in infos:
				if info.state != "post":
					continue

				try:
					summary = espn.fetch_summary(info.event_id)

				except requests.RequestException as exc:
					self.stderr.write(f"{info.event_id}: summary failed ({exc}); skipping game")
					continue

				espn.save_snapshot(summary, info.event_id)
				lines = extract.extract_player_lines(summary)
				report = crosswalk.map_espn_ids({line.espn_id: line.display_name for line in lines})
				unmatched.update(report["unmatched"] + report["ambiguous"])
				game = ingest.upsert_game(info)
				game.status = NbaGame.STATUS_SETTLED
				game.save()
				updated, _ = ingest.upsert_lines(game, lines, compiled)
				game.lines.update(is_final=True)
				games_done += 1
				lines_done += updated
				time.sleep(options["sleep"])

			self.stdout.write(f"{day}: done ({games_done} games, {lines_done} lines so far)")
			day += timedelta(days=1)

		self.stdout.write(self.style.SUCCESS(f"Backfilled {games_done} games, {lines_done} lines."))

		if unmatched:
			self.stdout.write("No unique league match for these ESPN names; set espn_id manually in Django admin:")

			for name in sorted(unmatched):
				self.stdout.write(f"  - {name}")
```

- [ ] **Step 6: Implement the parity command**

`scoring/management/commands/parity_check.py`:

```python
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from scoring.models import PlayerGameLine
from scoring.services.crosswalk import normalize_name


class Command(BaseCommand):
	"""Compare per-player fantasy point totals against a Fantrax CSV export (columns Player, FPts)."""

	help = "Compare per-player season fantasy point totals against a Fantrax CSV export"

	def add_arguments(self, parser) -> None:  # noqa: ANN001, D102, PLR6301
		parser.add_argument("csv_path")
		parser.add_argument("--tolerance", type=float, default=1.0, help="Max acceptable absolute delta per player")

	def handle(self, *_: Any, **options: Any) -> None:  # noqa: D102
		path = Path(options["csv_path"])

		if not path.exists():
			raise CommandError(f"No such file: {path}")

		ours: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

		for line in PlayerGameLine.objects.select_related("player").iterator():
			key = normalize_name(f"{line.player.first_name} {line.player.last_name}")
			ours[key] += line.fpts

		mismatches = []
		missing = []

		with path.open() as handle:
			for row in csv.DictReader(handle):
				expected = Decimal(str(row["FPts"]))

				if expected == 0:
					continue

				key = normalize_name(row["Player"])

				if key not in ours:
					missing.append(row["Player"])
					continue

				delta = ours[key] - expected

				if abs(delta) > Decimal("0.01"):
					mismatches.append((row["Player"], expected, ours[key], delta))

		for name, expected, actual, delta in sorted(mismatches, key=lambda item: -abs(item[3])):
			self.stdout.write(f"{name}: fantrax={expected} ours={actual} delta={delta:+}")

		if missing:
			self.stdout.write(f"Missing from our data ({len(missing)}): {', '.join(sorted(missing)[:20])}")

		worst = max((abs(delta) for *_ignored, delta in mismatches), default=Decimal("0"))

		if worst > Decimal(str(options["tolerance"])):
			raise CommandError(f"Parity FAILED: worst per-player delta {worst}")

		self.stdout.write(
			self.style.SUCCESS(f"Parity OK: {len(mismatches)} players off by <= {options['tolerance']}, worst {worst}")
		)
```

- [ ] **Step 7: Full suite, format, commit**

```bash
.venv/bin/python manage.py test scoring -v 1
ruff check --fix && ruff format
git add scoring/
git commit -m "feat: add espn crosswalk, season backfill, and fantrax parity check"
```

- [ ] **Step 8: Manual acceptance run (documents the real cutover check; do once, not in CI)**

```bash
# Backfill last season (regular season window), then compare with the league's Fantrax export.
.venv/bin/python manage.py backfill_season --start 2025-10-21 --end 2026-04-12
.venv/bin/python manage.py parity_check core/services/fantrax.csv
```

Expected: backfill reports games/lines and a short unmatched list (fix those in Django admin, re-run); parity requires the real league formula saved + activated first (create it via the builder UI or Django admin). Record the parity output in the PR/commit message.

---

### Task 10: frontend types, API service, and store

**Files (all in `/home/gtkacz/Codes/ftt/ftt-app`):**
- Create: `src/types/scoring.ts`, `src/api/scoring.ts`, `src/stores/scoring.ts`

**Interfaces:**
- Consumes: backend endpoints from Task 8; existing `src/api/axios.ts` default export.
- Produces (consumed by Task 11): types `ScoringField`, `ScoringRule`, `ScoringGame`, `PreviewRow`, `PreviewResponse`, `FormulaApiError`; `ScoringService` methods `getFields()`, `getGames(date?)`, `getRules()`, `createRule(data)`, `updateRule(id, data)`, `previewRule(formula_text, espn_event_id)`, `activateRule(id)`, `recomputeRule(id)`; Pinia store `useScoringStore` with state `{fields, rules, isLoading}` and actions `fetchFields`, `fetchRules`, `saveRule(data, id?)`, `activate(id)`, `recompute(id)`.

- [ ] **Step 1: Create `src/types/scoring.ts`**

```typescript
export type FieldSource = "box" | "derived" | "pbp" | "context";

export interface ScoringField {
  name: string;
  label: string;
  description: string;
  example: number;
  source: FieldSource;
}

export interface ScoringRule {
  id: number;
  name: string;
  formula_text: string;
  weights_json: Record<string, number> | null;
  is_active: boolean;
  updated_at: string;
}

export interface ScoringRuleRequest {
  name: string;
  formula_text: string;
  weights_json: Record<string, number> | null;
}

export interface ScoringGame {
  espn_event_id: string;
  starts_at: string;
  status: string;
  label: string;
}

export interface PreviewRow {
  player_name: string;
  espn_id: string | null;
  stats: Record<string, number>;
  fpts: string;
  active_fpts: string;
  delta: string;
}

export interface PreviewResponse {
  players: PreviewRow[];
}

export interface FormulaApiError {
  error: string;
  position: number | null;
  suggestion: string | null;
}
```

- [ ] **Step 2: Create `src/api/scoring.ts` (mirrors `src/api/users.ts` style)**

```typescript
import api from "./axios";
import type {
  PreviewResponse,
  ScoringField,
  ScoringGame,
  ScoringRule,
  ScoringRuleRequest,
} from "@/types/scoring";

export const ScoringService = {
  async getFields(): Promise<ScoringField[]> {
    const response = await api.get("/api/scoring/fields/");
    return response.data;
  },

  async getGames(date?: string): Promise<ScoringGame[]> {
    const params = date ? { date } : {};
    const response = await api.get("/api/scoring/games/", { params });
    return response.data;
  },

  async getRules(): Promise<ScoringRule[]> {
    const response = await api.get("/api/scoring/rules/");
    return response.data.results ?? response.data;
  },

  async createRule(data: ScoringRuleRequest): Promise<ScoringRule> {
    const response = await api.post("/api/scoring/rules/", data);
    return response.data;
  },

  async updateRule(id: number, data: ScoringRuleRequest): Promise<ScoringRule> {
    const response = await api.put(`/api/scoring/rules/${id}/`, data);
    return response.data;
  },

  async previewRule(formula_text: string, espn_event_id: string): Promise<PreviewResponse> {
    const response = await api.post("/api/scoring/rules/preview/", { formula_text, espn_event_id });
    return response.data;
  },

  async activateRule(id: number): Promise<{ is_active: boolean; updated: number }> {
    const response = await api.post(`/api/scoring/rules/${id}/activate/`);
    return response.data;
  },

  async recomputeRule(id: number): Promise<{ updated: number }> {
    const response = await api.post(`/api/scoring/rules/${id}/recompute/`);
    return response.data;
  },
};
```

- [ ] **Step 3: Create `src/stores/scoring.ts` (options style, like `src/stores/settings.ts`)**

```typescript
import { defineStore } from "pinia";
import { ScoringService } from "@/api/scoring";
import type { ScoringField, ScoringRule, ScoringRuleRequest } from "@/types/scoring";

interface ScoringState {
  fields: ScoringField[];
  rules: ScoringRule[];
  isLoading: boolean;
}

export const useScoringStore = defineStore("scoring", {
  state: (): ScoringState => ({
    fields: [],
    rules: [],
    isLoading: false,
  }),

  getters: {
    activeRule(state): ScoringRule | null {
      return state.rules.find((rule) => rule.is_active) ?? null;
    },
  },

  actions: {
    async fetchFields(): Promise<void> {
      if (this.fields.length > 0) return;
      this.fields = await ScoringService.getFields();
    },

    async fetchRules(): Promise<void> {
      this.isLoading = true;
      try {
        this.rules = await ScoringService.getRules();
      } finally {
        this.isLoading = false;
      }
    },

    async saveRule(data: ScoringRuleRequest, id?: number): Promise<ScoringRule> {
      const saved = id === undefined
        ? await ScoringService.createRule(data)
        : await ScoringService.updateRule(id, data);
      await this.fetchRules();
      return saved;
    },

    async activate(id: number): Promise<number> {
      const result = await ScoringService.activateRule(id);
      await this.fetchRules();
      return result.updated;
    },

    async recompute(id: number): Promise<number> {
      const result = await ScoringService.recomputeRule(id);
      return result.updated;
    },
  },
});
```

- [ ] **Step 4: Verify types compile**

Run: `bun run lintbuild`
Expected: exits 0 (vue-tsc + vite build succeed).

- [ ] **Step 5: Commit (in ftt-app)**

```bash
git add src/types/scoring.ts src/api/scoring.ts src/stores/scoring.ts
git commit -m "feat: add scoring types, api service, and store"
```

---

### Task 11: builder UI (grid + formula + preview) and navigation

**Files (all in `/home/gtkacz/Codes/ftt/ftt-app`):**
- Create: `src/components/scoring/FieldPalette.vue`, `src/components/scoring/WeightsGrid.vue`, `src/components/scoring/FormulaEditor.vue`, `src/components/scoring/PreviewPanel.vue`, `src/views/admin/ScoringRuleBuilderView.vue`
- Modify: `src/router/index.ts` (child route under the existing `/commission` route), `src/components/layout/navItems.ts` (commissioner nav entry)

**Interfaces:**
- Consumes: Task 10's `useScoringStore`, `ScoringService`, types; existing `/commission` route with `meta.requiresStaff`; `NavItem`'s `commission_only` prop plumbing.
- Produces: route `commission-scoring` at `/commission/scoring`.

- [ ] **Step 1: Create `src/components/scoring/FieldPalette.vue`**

```vue
<template>
  <div class="field-palette">
    <div v-for="group in groups" :key="group.source" class="palette-group">
      <div class="text-caption text-uppercase mb-1">{{ group.title }}</div>
      <v-chip-group column>
        <v-tooltip v-for="field in group.fields" :key="field.name" :text="`${field.description} (e.g. ${field.example})`" location="top">
          <template #activator="{ props }">
            <v-chip v-bind="props" size="small" @click="emit('insert', field.name)">{{ field.name }}</v-chip>
          </template>
        </v-tooltip>
      </v-chip-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { FieldSource, ScoringField } from "@/types/scoring";

const props = defineProps<{ fields: ScoringField[] }>();
const emit = defineEmits<{ insert: [name: string] }>();

const titles: Record<FieldSource, string> = {
  box: "Box score",
  derived: "Derived",
  pbp: "Play-by-play",
  context: "Game context",
};

const groups = computed(() =>
  (Object.keys(titles) as FieldSource[]).map((source) => ({
    source,
    title: titles[source],
    fields: props.fields.filter((field) => field.source === source),
  })).filter((group) => group.fields.length > 0),
);
</script>
```

- [ ] **Step 2: Create `src/components/scoring/WeightsGrid.vue`**

```vue
<template>
  <v-table density="compact">
    <thead>
      <tr>
        <th>Field</th>
        <th>Description</th>
        <th style="width: 140px">Weight</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="field in fields" :key="field.name">
        <td><code>{{ field.name }}</code></td>
        <td class="text-caption">{{ field.description }}</td>
        <td>
          <v-text-field
            :model-value="modelValue[field.name] ?? 0"
            type="number"
            step="0.1"
            density="compact"
            hide-details
            variant="outlined"
            @update:model-value="setWeight(field.name, $event)"
          />
        </td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
import type { ScoringField } from "@/types/scoring";

const props = defineProps<{
  fields: ScoringField[];
  modelValue: Record<string, number>;
}>();
const emit = defineEmits<{ "update:modelValue": [value: Record<string, number>] }>();

function setWeight(name: string, raw: string): void {
  const parsed = Number(raw);
  emit("update:modelValue", { ...props.modelValue, [name]: Number.isFinite(parsed) ? parsed : 0 });
}
</script>
```

- [ ] **Step 3: Create `src/components/scoring/FormulaEditor.vue`**

```vue
<template>
  <div>
    <v-textarea
      :model-value="modelValue"
      class="formula-input"
      rows="4"
      auto-grow
      variant="outlined"
      placeholder="1*PTS + 1.2*OREB + 1*DREB + 1.5*AST - 0.5*FT_MISS + 5*DD + 10*TD"
      hint="Allowed: numbers, fields, + - * / ( ) and comparisons (evaluate to 0/1). Division by zero is 0."
      persistent-hint
      @update:model-value="emit('update:modelValue', $event)"
    />
    <v-alert v-if="error" type="error" density="compact" class="mt-2" variant="tonal">
      {{ error.error }}
      <template v-if="error.suggestion"> — did you mean <code>{{ error.suggestion }}</code>?</template>
      <template v-if="error.position !== null"> (position {{ error.position }})</template>
    </v-alert>
  </div>
</template>

<script setup lang="ts">
import type { FormulaApiError } from "@/types/scoring";

defineProps<{
  modelValue: string;
  error: FormulaApiError | null;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<style scoped>
.formula-input :deep(textarea) {
  font-family: monospace;
}
</style>
```

- [ ] **Step 4: Create `src/components/scoring/PreviewPanel.vue`**

```vue
<template>
  <v-card variant="outlined">
    <v-card-title class="text-subtitle-1">Live preview against a real game</v-card-title>
    <v-card-text>
      <div class="d-flex ga-2 mb-3">
        <v-text-field v-model="dateStr" type="date" label="Game date" density="compact" hide-details style="max-width: 200px" />
        <v-select
          v-model="eventId"
          :items="games"
          item-title="label"
          item-value="espn_event_id"
          label="Game"
          density="compact"
          hide-details
          :no-data-text="dateStr ? 'No ingested games on this date' : 'Pick a date'"
        />
      </div>
      <v-alert v-if="error" type="warning" density="compact" variant="tonal" class="mb-2">{{ error.error }}</v-alert>
      <v-table v-if="rows.length > 0" density="compact">
        <thead>
          <tr><th>Player</th><th class="text-right">Draft rule</th><th class="text-right">Active rule</th><th class="text-right">Δ</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.player_name">
            <td>{{ row.player_name }}</td>
            <td class="text-right">{{ row.fpts }}</td>
            <td class="text-right">{{ row.active_fpts }}</td>
            <td class="text-right" :class="deltaClass(row.delta)">{{ row.delta }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { isAxiosError } from "axios";
import { ScoringService } from "@/api/scoring";
import type { FormulaApiError, PreviewRow, ScoringGame } from "@/types/scoring";

const props = defineProps<{ formulaText: string }>();
const emit = defineEmits<{ formulaError: [error: FormulaApiError | null] }>();

const dateStr = ref("");
const games = ref<ScoringGame[]>([]);
const eventId = ref<string | null>(null);
const rows = ref<PreviewRow[]>([]);
const error = ref<FormulaApiError | null>(null);
let debounceHandle: ReturnType<typeof setTimeout> | null = null;

watch(dateStr, async (value) => {
  games.value = value ? await ScoringService.getGames(value) : [];
  eventId.value = games.value[0]?.espn_event_id ?? null;
});

watch([() => props.formulaText, eventId], () => {
  if (debounceHandle) clearTimeout(debounceHandle);
  debounceHandle = setTimeout(refresh, 500);
});

async function refresh(): Promise<void> {
  error.value = null;
  emit("formulaError", null);
  if (!eventId.value || !props.formulaText.trim()) {
    rows.value = [];
    return;
  }
  try {
    const response = await ScoringService.previewRule(props.formulaText, eventId.value);
    rows.value = response.players;
  } catch (err: unknown) {
    rows.value = [];
    if (isAxiosError(err) && err.response && (err.response.status === 400 || err.response.status === 404)) {
      error.value = err.response.data as FormulaApiError;
      if (err.response.status === 400) emit("formulaError", error.value);
      return;
    }
    throw err;
  }
}

function deltaClass(delta: string): string {
  const value = Number(delta);
  if (value > 0) return "text-success";
  if (value < 0) return "text-error";
  return "";
}
</script>
```

- [ ] **Step 5: Create `src/views/admin/ScoringRuleBuilderView.vue`**

```vue
<template>
  <v-container fluid>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h5">Scoring rules</h1>
      <v-chip v-if="store.activeRule" class="ml-3" color="success" size="small">active: {{ store.activeRule.name }}</v-chip>
    </div>

    <v-row>
      <v-col cols="12" md="7">
        <v-text-field v-model="name" label="Rule name" density="compact" variant="outlined" style="max-width: 320px" />

        <v-tabs v-model="tab" density="compact">
          <v-tab value="grid" :disabled="!gridAvailable">Grid</v-tab>
          <v-tab value="formula">Formula</v-tab>
        </v-tabs>

        <v-window v-model="tab" class="mt-3">
          <v-window-item value="grid">
            <v-alert v-if="!gridAvailable" type="info" density="compact" variant="tonal" class="mb-2">
              This rule uses an advanced formula; edit it in the Formula tab.
            </v-alert>
            <WeightsGrid v-else v-model="weights" :fields="store.fields" />
          </v-window-item>

          <v-window-item value="formula">
            <FieldPalette :fields="store.fields" class="mb-2" @insert="appendField" />
            <FormulaEditor v-model="formulaText" :error="formulaError" />
          </v-window-item>
        </v-window>

        <div class="d-flex ga-2 mt-4">
          <v-btn color="primary" :loading="saving" @click="confirmOpen = true">Save & apply</v-btn>
        </div>
      </v-col>

      <v-col cols="12" md="5">
        <PreviewPanel :formula-text="effectiveFormula" @formula-error="formulaError = $event" />
      </v-col>
    </v-row>

    <v-dialog v-model="confirmOpen" max-width="480">
      <v-card>
        <v-card-title>Apply scoring rule?</v-card-title>
        <v-card-text>
          Saving recomputes fantasy points for every stored player-game line this season.
          Matchup totals everywhere will restate under the new formula.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmOpen = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Apply</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="toastOpen" timeout="6000">{{ toastText }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { isAxiosError } from "axios";
import FieldPalette from "@/components/scoring/FieldPalette.vue";
import FormulaEditor from "@/components/scoring/FormulaEditor.vue";
import PreviewPanel from "@/components/scoring/PreviewPanel.vue";
import WeightsGrid from "@/components/scoring/WeightsGrid.vue";
import { useScoringStore } from "@/stores/scoring";
import type { FormulaApiError } from "@/types/scoring";

const store = useScoringStore();

const tab = ref<"grid" | "formula">("grid");
const name = ref("League scoring");
const weights = ref<Record<string, number>>({});
const formulaText = ref("");
const formulaError = ref<FormulaApiError | null>(null);
const confirmOpen = ref(false);
const toastOpen = ref(false);
const toastText = ref("");
const saving = ref(false);

// A rule authored in formula mode has weights_json null; the grid can't represent it.
const gridAvailable = computed(() => store.activeRule === null || store.activeRule.weights_json !== null);

const gridFormula = computed(() =>
  Object.entries(weights.value)
    .filter(([, weight]) => weight !== 0)
    .map(([field, weight]) => `${weight}*${field}`)
    .join(" + ")
    .replaceAll("+ -", "- "),
);

const effectiveFormula = computed(() => (tab.value === "grid" && gridAvailable.value ? gridFormula.value : formulaText.value));

onMounted(async () => {
  await Promise.all([store.fetchFields(), store.fetchRules()]);
  const active = store.activeRule;
  if (active) {
    name.value = active.name;
    formulaText.value = active.formula_text;
    weights.value = active.weights_json ?? {};
    tab.value = active.weights_json === null ? "formula" : "grid";
  }
});

watch(gridFormula, (value) => {
  if (tab.value === "grid") formulaText.value = value;
});

function appendField(fieldName: string): void {
  formulaText.value = formulaText.value.trim() === "" ? fieldName : `${formulaText.value} + ${fieldName}`;
}

async function save(): Promise<void> {
  saving.value = true;
  formulaError.value = null;
  try {
    const fromGrid = tab.value === "grid" && gridAvailable.value;
    const saved = await store.saveRule(
      {
        name: name.value,
        formula_text: effectiveFormula.value,
        weights_json: fromGrid ? weights.value : null,
      },
      store.activeRule?.id,
    );
    const updated = await store.activate(saved.id);
    toastText.value = `Applied. Recomputed ${updated.toLocaleString()} player-game lines.`;
    toastOpen.value = true;
    confirmOpen.value = false;
  } catch (err: unknown) {
    if (isAxiosError(err) && err.response?.status === 400) {
      const data = err.response.data as Record<string, unknown>;
      const message = Array.isArray(data.formula_text) ? String(data.formula_text[0]) : JSON.stringify(data);
      formulaError.value = { error: message, position: null, suggestion: null };
      tab.value = "formula";
      confirmOpen.value = false;
      return;
    }
    throw err;
  } finally {
    saving.value = false;
  }
}
</script>
```

- [ ] **Step 6: Register the route and nav item**

In `src/router/index.ts`, inside the existing `/commission` route's `children` array, add:

```typescript
      {
        path: "scoring",
        name: "commission-scoring",
        component: () => import("@/views/admin/ScoringRuleBuilderView.vue"),
        meta: {
          title: "Scoring Rules - Fantasy Trash Talk",
          requiresStaff: true,
        },
      },
```

In `src/components/layout/navItems.ts`, add to the commissioner-only group's `items` array (the group whose items carry `commission_only: true`):

```typescript
    {
      icon: "mdi-calculator-variant",
      label: "Scoring",
      routeName: "commission-scoring",
      commission_only: true,
    },
```

If the item type requires other keys (`params`, `disabled`, `devonly`), match the neighboring entries' shape exactly.

- [ ] **Step 7: Build check**

Run: `cd /home/gtkacz/Codes/ftt/ftt-app && bun run lintbuild`
Expected: exits 0.

- [ ] **Step 8: Manual verification checklist (needs backend running with backfilled data)**

```bash
# Terminal 1 (ftt-server): .venv/bin/python manage.py runserver
# Terminal 2 (ftt-app):    bun run dev
```

- Log in as a superuser → "Scoring" appears in the commissioner nav group; `/commission/scoring` loads.
- Palette shows all 27 fields grouped in four sections with description tooltips.
- Grid tab: setting PTS=1, AST=1.5 updates the Formula tab text to `1*PTS + 1.5*AST`.
- Formula tab: typing `1*FTMISS` shows the inline error with the `FT_MISS` suggestion (after picking a game in preview).
- Preview: pick a backfilled date → game → table shows players with draft-rule points, active-rule points, and a signed colored delta; edits re-preview after ~0.5 s.
- Save & apply → confirm dialog mentions full-season recompute → success toast reports the recomputed line count.
- Log in as a non-staff user → no "Scoring" nav item; navigating to `/commission/scoring` is blocked by the router guard; `POST /api/scoring/rules/` returns 403.

- [ ] **Step 9: Commit (in ftt-app)**

```bash
git add src/components/scoring/ src/views/admin/ScoringRuleBuilderView.vue src/router/index.ts src/components/layout/navItems.ts
git commit -m "feat: add commissioner scoring rule builder with live preview"
```

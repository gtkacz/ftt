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
			"MIN": 33, "PTS": 5, "FGM": 2, "FGA": 9, "TPM": 1, "TPA": 7,
			"FTM": 0, "FTA": 0, "REB": 5, "AST": 3, "TO": 0, "STL": 4,
			"BLK": 0, "OREB": 0, "DREB": 5, "PF": 1, "PLUS_MINUS": -4,
			"FG_MISS": 7, "TP_MISS": 6, "FT_MISS": 0, "DD": 0, "TD": 0,
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

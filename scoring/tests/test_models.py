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
			index=1,
			starts_at=now - timedelta(days=1),
			ends_at=now + timedelta(days=6),
		)
		self.assertEqual(ScoringPeriod.for_datetime(now), period)
		self.assertIsNone(ScoringPeriod.for_datetime(now + timedelta(days=30)))


class PlayerGameLineTests(TestCase):
	def setUp(self) -> None:
		# core.0014_nbateam_datamigration seeds real NBA teams (incl. this one) into the
		# test DB, so get_or_create avoids an IntegrityError on the unique abbreviation.
		self.team, _ = NBATeam.objects.get_or_create(city="San Antonio", name="Spurs", abbreviation="SAS")
		self.player = Player.objects.create(
			first_name="Julian",
			last_name="Champagnie",
			primary_position="F",
			espn_id="4433134",
		)
		self.game = NbaGame.objects.create(
			espn_event_id="401859966",
			starts_at=timezone.now(),
			home=self.team,
			away=self.team,
		)

	def test_line_unique_per_player_and_game(self) -> None:
		PlayerGameLine.objects.create(player=self.player, game=self.game, raw_stats={"PTS": 5})
		with self.assertRaises(IntegrityError), transaction.atomic():
			PlayerGameLine.objects.create(player=self.player, game=self.game, raw_stats={"PTS": 6})

	def test_espn_id_unique_on_player(self) -> None:
		with self.assertRaises(IntegrityError), transaction.atomic():
			Player.objects.create(first_name="Copy", last_name="Cat", primary_position="G", espn_id="4433134")

from random import shuffle

from django.db import models, transaction

from core.models import Notification, Player


class Draft(models.Model):
	"""Represents a draft event."""

	year = models.PositiveIntegerField()
	draftable_players = models.ManyToManyField("core.Player", related_name="drafts", blank=True)
	is_completed = models.BooleanField(default=False)
	is_league_draft = models.BooleanField(default=False)
	teams = models.ManyToManyField(
		"core.Team",
		related_name="drafts",
		blank=True,
		help_text="Teams participating in the draft",
	)
	rounds = models.PositiveIntegerField(default=2, help_text="Number of rounds in the draft")
	starts_at = models.DateTimeField(null=True, blank=True, help_text="Start time of the draft")
	time_limit_per_pick = models.PositiveIntegerField(default=180, help_text="Time limit in minutes for each pick")
	pick_hour_lower_bound = models.PositiveIntegerField(
		default=8,
		help_text="Lower bound for the hour of the day when picks can be made",
	)
	pick_hour_upper_bound = models.PositiveIntegerField(
		default=22,
		help_text="Upper bound for the hour of the day when picks can be made",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("-year",)
		unique_together = ("year", "is_league_draft")

	def __str__(self) -> str:
		return f"{self.year} Draft"

	def current_player_pool(self) -> models.QuerySet[Player]:
		"""Returns the list of players still available for drafting."""
		return self.draftable_players.filter(contract__isnull=True)

	def drafted_players(self) -> models.QuerySet[Player]:
		"""Returns the list of players that have been drafted in this draft."""
		return self.draftable_players.filter(contract__isnull=False)

	def generate_draft_order(self) -> list[int]:
		"""Generates a snake draft order based on the list of teams."""  # noqa: DOC201
		teams = list(self.teams.all().values_list("id", flat=True))

		teams_order = list(teams)
		shuffle(teams_order)

		return teams_order

	def evaluate_pick_protections(self, pick_positions: dict[int, int]) -> None:
		"""
		Evaluate pick protections based on actual draft positions.

		Args:
			pick_positions: Dict mapping pick_id to actual pick number (1-based)
				Example: {pick1.id: 3, pick2.id: 15} means pick1 is #3 overall, pick2 is #15
		"""
		from draft.models import Pick  # noqa: PLC0415

		# Get all picks for this draft year with protections
		protected_picks = Pick.objects.filter(
			draft_year=self.year,
			protection_type__in=["swap_best", "swap_worst", "doesnt_convey"],
		)

		# First pass: set actual pick numbers
		for pick in protected_picks:
			if pick.id in pick_positions:
				pick.actual_pick_number = pick_positions[pick.id]
				pick.save()

		# Second pass: evaluate protections
		for pick in protected_picks:
			if pick.id in pick_positions:
				result = pick.evaluate_protection(pick_positions[pick.id])
				pick.apply_protection_result(result)

	def start(self) -> list[int]:
		"""
		Starts the draft and generates the draft order.

		IMPORTANT: Call evaluate_pick_protections() BEFORE calling this method if:
		- This is not a league draft (is_league_draft=False)
		- You have pick protections that need to be evaluated
		- You have determined actual pick positions (from lottery/standings)

		Example:
			# Determine pick positions (e.g., from standings or lottery)
			pick_positions = {pick1.id: 3, pick2.id: 15}  # pick1 is #3, pick2 is #15
			draft.evaluate_pick_protections(pick_positions)
			draft.start()

		Raises:
			ValueError: If the draft is already completed.
			ValueError: If the draft has no teams.
			ValueError: If the draft has no draftable players.

		Returns:
			list[int]: The draft order.
		"""
		if self.is_completed:
			raise ValueError("Draft is already completed")

		if not self.teams.exists():
			raise ValueError("Draft must have at least one team")

		if not self.draftable_players.exists():
			raise ValueError("Draft must have at least one draftable player")

		with transaction.atomic():
			from draft.models import DraftPick, Pick  # noqa: PLC0415

			teams_order = self.generate_draft_order()
			picks = Pick.objects.none() if self.is_league_draft else Pick.objects.filter(draft_year=self.year)

			DraftPick.objects.filter(draft=self).delete()

			overall_pick = 1

			for round_num in range(1, self.rounds + 1):
				pick_order = teams_order if round_num % 2 == 1 else teams_order[::-1]

				for pick_num, team_id in enumerate(pick_order, 1):
					current_pick = (
						Pick.objects.create(
							original_team_id=team_id,
							current_team_id=team_id,
							draft_year=self.year,
							round_number=round_num,
							is_from_league_draft=True,
						)
						if self.is_league_draft
						else picks.filter(
							current_team_id=team_id,
							round_number=round_num,
							is_from_league_draft=False,
						).first()
					)

					draft_pick = DraftPick.objects.create(
						draft=self,
						pick=current_pick,
						pick_number=pick_num,
						overall_pick=overall_pick,
						is_current=(overall_pick == 1),
					)

					Notification.objects.create(
						user=current_pick.current_team.owner,  # pyright: ignore[reportOptionalMemberAccess]
						message=f"Your team has the {overall_pick} pick in the {self.year} {'league' if self.is_league_draft else ''} draft!",
					)

					current_contract = draft_pick.generate_contract()
					draft_pick.contract = current_contract  # pyright: ignore[reportAttributeAccessIssue]
					draft_pick.save()

					overall_pick += 1

			self.save()

			return teams_order

	def print_picks(self, *, recent_only: bool = False) -> None:
		"""Prints the draft picks in order."""
		from draft.models import DraftPick  # noqa: PLC0415

		output = []
		start_at_round = (
			1 if not recent_only else self.draft_positions.filter(is_current=True).first().pick.round_number - 1  # pyright: ignore[reportAttributeAccessIssue]
		)

		for i in range(
			DraftPick.objects.filter(draft=self, pick__round_number=start_at_round).first().overall_pick,  # pyright: ignore[reportOptionalMemberAccess]
			1000,
		):
			curr = DraftPick.objects.filter(overall_pick=i)

			if not curr.exists() or not curr.first().is_pick_made:  # pyright: ignore[reportOptionalMemberAccess]
				break

			curr = curr.first()
			output.append(f"{curr} - {curr.selected_player}")  # pyright: ignore[reportOptionalMemberAccess]

		for item in output:
			print(item)  # noqa: T201

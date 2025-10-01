from django.core.exceptions import ValidationError
from django.db import models


class Pick(models.Model):
	"""Represents draft capital/assets that teams own."""

	PROTECTION_TYPE_CHOICES = [
		("none", "No Protection"),
		("swap_best", "Swap if Best"),  # Swap if pick is better than expected
		("swap_worst", "Swap if Worst"),  # Swap if pick is worse than expected
		("doesnt_convey", "Doesn't Convey"),  # Pick doesn't transfer if in protected range
	]

	original_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="original_picks")
	current_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="current_picks")
	draft_year = models.PositiveIntegerField()
	round_number = models.PositiveIntegerField()
	is_from_league_draft = models.BooleanField(default=False, help_text="Indicates if this pick is from a league draft")

	# Protection fields
	protection_type = models.CharField(
		max_length=20,
		choices=PROTECTION_TYPE_CHOICES,
		default="none",
		help_text="Type of protection on this pick",
	)

	protection_range_start = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Start of protected pick range (e.g., 1 for top-5 protected)",
	)

	protection_range_end = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="End of protected pick range (e.g., 5 for top-5 protected)",
	)

	swap_target_pick = models.ForeignKey(
		"self",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="swap_sources",
		help_text="Pick to swap with if protection is triggered (for swap_best/swap_worst)",
	)

	rollover_year = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Year pick rolls over to if it doesn't convey",
	)

	# Draft position tracking
	actual_pick_number = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Actual pick number after lottery/standings (1-30 for round 1)",
	)

	is_conveyed = models.BooleanField(
		default=True,
		help_text="Whether this pick conveyed to current_team or was protected",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("draft_year", "round_number")
		unique_together = ("original_team", "draft_year", "round_number")
		indexes = [
			models.Index(fields=["draft_year", "current_team"]),
			models.Index(fields=["protection_type"]),
		]

	def __str__(self) -> str:
		protection_str = self._get_protection_display_string()
		return f"{self.draft_year} Round {self.round_number} - {self.current_team.name}{protection_str}"

	def _get_protection_display_string(self) -> str:
		"""Generate a human-readable protection description."""
		if self.protection_type == "none":
			return ""

		if self.protection_type == "doesnt_convey" and self.protection_range_start and self.protection_range_end:
			return f" (Doesn't convey if picks {self.protection_range_start}-{self.protection_range_end})"

		if self.protection_type == "swap_best" and self.swap_target_pick:
			return f" (Swap to best with {self.swap_target_pick.original_team.name})"

		if self.protection_type == "swap_worst" and self.swap_target_pick:
			return f" (Swap to worst with {self.swap_target_pick.original_team.name})"

		return f" ({self.get_protection_type_display()})"

	def clean(self) -> None:
		"""Validate pick protection configuration."""
		super().clean()

		if self.protection_type == "none":
			return

		# Validate swap protections
		if self.protection_type in ["swap_best", "swap_worst"]:
			if not self.swap_target_pick:
				raise ValidationError(
					f"swap_target_pick is required for protection type '{self.protection_type}'"
				)

			if self.swap_target_pick == self:
				raise ValidationError("Cannot swap pick with itself")

			if self.swap_target_pick.draft_year != self.draft_year:
				raise ValidationError("Can only swap picks from the same draft year")

			if self.swap_target_pick.round_number != self.round_number:
				raise ValidationError("Can only swap picks from the same round")

		# Validate doesn't convey protection
		if self.protection_type == "doesnt_convey":
			if not self.protection_range_start or not self.protection_range_end:
				raise ValidationError(
					"protection_range_start and protection_range_end are required for 'doesnt_convey' protection"
				)

			if self.protection_range_start > self.protection_range_end:
				raise ValidationError("protection_range_start must be <= protection_range_end")

			if not self.rollover_year:
				raise ValidationError("rollover_year is required for 'doesnt_convey' protection")

			if self.rollover_year <= self.draft_year:
				raise ValidationError("rollover_year must be after draft_year")

	def evaluate_protection(self, actual_pick_number: int) -> dict[str, any]:  # noqa: C901
		"""
		Evaluate if protection is triggered and determine the outcome.

		Args:
			actual_pick_number: The actual draft position (1-30 for round 1)

		Returns:
			dict with keys:
				- triggered: bool - whether protection was triggered
				- action: str - what action to take (swap/rollover/convey)
				- swap_with: Pick | None - pick to swap with if applicable
				- rollover_to_year: int | None - year to roll over to if applicable
		"""
		self.actual_pick_number = actual_pick_number

		result = {
			"triggered": False,
			"action": "convey",
			"swap_with": None,
			"rollover_to_year": None,
		}

		if self.protection_type == "none":
			self.is_conveyed = True
			self.save()
			return result

		# Evaluate doesn't convey protection
		if self.protection_type == "doesnt_convey":
			if (
				self.protection_range_start
				and self.protection_range_end
				and self.protection_range_start <= actual_pick_number <= self.protection_range_end
			):
				result["triggered"] = True
				result["action"] = "rollover"
				result["rollover_to_year"] = self.rollover_year
				self.is_conveyed = False
				self.save()
				return result

		# Evaluate swap protections
		if self.protection_type in ["swap_best", "swap_worst"] and self.swap_target_pick:
			# Get the swap target's actual pick number
			if not self.swap_target_pick.actual_pick_number:
				raise ValidationError("Swap target pick must have actual_pick_number set")

			target_pick_number = self.swap_target_pick.actual_pick_number

			should_swap = False
			if self.protection_type == "swap_best":
				# Swap if this pick is better (lower number) than target
				should_swap = actual_pick_number < target_pick_number
			elif self.protection_type == "swap_worst":
				# Swap if this pick is worse (higher number) than target
				should_swap = actual_pick_number > target_pick_number

			if should_swap:
				result["triggered"] = True
				result["action"] = "swap"
				result["swap_with"] = self.swap_target_pick
				self.save()
				return result

		# Protection wasn't triggered - pick conveys normally
		self.is_conveyed = True
		self.save()
		return result

	def apply_protection_result(self, protection_result: dict[str, any]) -> None:
		"""
		Apply the protection evaluation result to this pick.

		Args:
			protection_result: Result from evaluate_protection()
		"""
		if not protection_result["triggered"]:
			return

		if protection_result["action"] == "swap" and protection_result["swap_with"]:
			# Swap current_team with the swap target
			target_pick = protection_result["swap_with"]
			self.current_team, target_pick.current_team = target_pick.current_team, self.current_team
			self.save()
			target_pick.save()

		elif protection_result["action"] == "rollover" and protection_result["rollover_to_year"]:
			# Create a new pick for the rollover year
			Pick.objects.create(
				original_team=self.original_team,
				current_team=self.original_team,  # Reverts to original team
				draft_year=protection_result["rollover_to_year"],
				round_number=self.round_number,
				protection_type="none",  # Rolled over picks typically have no protection
			)
			self.is_conveyed = False
			self.save()

	@staticmethod
	def create_protected_pick(
		original_team: "Team",  # noqa: F821
		current_team: "Team",  # noqa: F821
		draft_year: int,
		round_number: int,
		protection_type: str = "none",
		**kwargs: dict[str, any],
	) -> "Pick":
		"""
		Helper method to create a pick with protections.

		Args:
			original_team: Team that originally owned the pick
			current_team: Team that currently owns the pick
			draft_year: Year of the draft
			round_number: Round number
			protection_type: Type of protection
			**kwargs: Additional fields (protection_range_start, protection_range_end, etc.)

		Returns:
			Created Pick instance
		"""
		pick = Pick(
			original_team=original_team,
			current_team=current_team,
			draft_year=draft_year,
			round_number=round_number,
			protection_type=protection_type,
			**kwargs,
		)
		pick.full_clean()
		pick.save()
		return pick

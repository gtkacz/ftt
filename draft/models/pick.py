from django.db import models


class Pick(models.Model):
	"""Represents draft capital/assets that teams own."""

	original_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="original_picks")
	current_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="current_picks")
	draft_year = models.PositiveIntegerField()
	round_number = models.PositiveIntegerField()
	is_from_league_draft = models.BooleanField(default=False, help_text="Indicates if this pick is from a league draft")

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
		indexes = (models.Index(fields=["draft_year", "current_team"]),)

	def __str__(self) -> str:
		return f"{self.draft_year} Round {self.round_number} - {self.current_team.name}"

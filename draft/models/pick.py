from django.db import models


class Pick(models.Model):
	"""Represents draft capital/assets that teams own."""

	original_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="original_picks")
	current_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="current_picks")
	draft_year = models.PositiveIntegerField()
	protections = models.TextField(blank=True, help_text="Description of pick protections")
	round_number = models.PositiveIntegerField()
	is_from_league_draft = models.BooleanField(default=False, help_text="Indicates if this pick is from a league draft")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("draft_year", "round_number")
		unique_together = ("original_team", "draft_year", "round_number")

	def __str__(self) -> str:
		return f"{self.draft_year} Round {self.round_number} - {self.current_team.name}"

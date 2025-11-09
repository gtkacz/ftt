from collections.abc import Sequence
from typing import Any

from django.db import models


class Player(models.Model):
	"""Model representing a basketball player."""

	POSITION_CHOICES = (
		("G", "Guard"),
		("F", "Forward"),
		("C", "Center"),
	)

	first_name = models.CharField(max_length=100)
	last_name = models.CharField(max_length=100)
	primary_position = models.CharField(max_length=1, choices=POSITION_CHOICES)
	secondary_position = models.CharField(max_length=1, choices=POSITION_CHOICES, blank=True)
	nba_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
	is_ir = models.BooleanField(default=False, help_text="Injury Reserve")
	real_team = models.ForeignKey(
		"NBATeam",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="players",
	)
	slug = models.SlugField(max_length=100, unique=True, null=True, blank=True)
	metadata = models.JSONField(default=dict, blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("last_name",)

	def __str__(self) -> str:
		return f"{self.first_name} {self.last_name}"

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride] # noqa: D102
		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

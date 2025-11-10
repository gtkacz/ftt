from enum import Enum
from json import loads

from django.core.exceptions import ValidationError
from django.db import models

from core.models import Notification

class Pick(models.Model):
	"""Draft capital/assets that teams own."""

	class ProtectionChoices(Enum):
		"""Enumeration of possible pick protection types."""

		UNPROTECTED = ("unprotected", "UNPROTECTED")
		TOP_X = ("top_x", "TOP_X")
		SWAP_BEST = ("swap_best", "SWAP_BEST")
		SWAP_WORST = ("swap_worst", "SWAP_WORST")

	original_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="original_picks")
	current_team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="current_picks")
	draft_year = models.PositiveIntegerField()
	round_number = models.PositiveIntegerField()
	is_from_league_draft = models.BooleanField(default=False, help_text="Indicates if this pick is from a league draft")
	protection = models.CharField(
		max_length=11,
		choices=ProtectionChoices._hashable_values_,
		default=ProtectionChoices.UNPROTECTED.value[0],
	)
	protection_metadata = models.JSONField(
		null=True,
		blank=True,
		help_text="Additional data related to the pick's protection (e.g., value of X for TOP_X protection)",
	)
	protection_conveyed = models.BooleanField(
		default=False, help_text="Indicates if the pick's protection has been conveyed to the receiving team",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("draft_year", "round_number")
		unique_together = ("original_team", "draft_year", "round_number")
		indexes = (models.Index(fields=["draft_year", "current_team"]),)

	def __str__(self) -> str:
		suffix = f" (via {self.original_team.name})" if self.current_team != self.original_team else ""
		return f"{self.draft_year} Round {self.round_number} - {self.current_team.name}{suffix}"

	def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
		"""Overrides the save method to notify users if a pick conveyed."""
		if self.protection_conveyed:
			Notification.objects.create(
				user=self.current_team.owner,
				message=f"Pick {self} has conveyed its protection.",
			)

		super().save(*args, **kwargs)

	@property
	def top_x_value(self) -> int:
		"""
		Gets the value of X for TOP_X protection.

		Raises:
			ValidationError: If the pick is TOP_X protected but metadata is missing.

		Returns:
			int: The value of X if the pick is TOP_X protected.
		"""
		if self.protection != self.ProtectionChoices.TOP_X.value[0]:
			raise ValidationError("Pick is not TOP_X protected.")

		if not self.protection_metadata:
			raise ValidationError("Protection metadata is required for TOP_X protection.")

		metadata = self.protection_metadata

		if isinstance(self.protection_metadata, str):
			metadata = loads(metadata)

		x_value = metadata.get("x_value", None)

		if x_value is None:
			raise ValidationError("x_value is missing in protection metadata for TOP_X protection.")

		return int(x_value)

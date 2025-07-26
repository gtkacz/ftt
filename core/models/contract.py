from collections.abc import Sequence
from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models.notification import Notification


class Contract(models.Model):
	"""Model representing a player's contract with a team."""

	player = models.OneToOneField("Player", on_delete=models.CASCADE, related_name="contract", null=True, blank=True)
	team = models.ForeignKey("Team", on_delete=models.CASCADE, related_name="contracts", null=True, blank=True)
	start_year = models.PositiveIntegerField()
	duration = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
	salary = models.DecimalField(max_digits=10, decimal_places=2)
	is_rfa = models.BooleanField(default=False, help_text="Restricted Free Agent")
	is_to = models.BooleanField(default=False, help_text="Team Option")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.player} - {self.team} ({self.start_year}-{self.start_year + self.duration - 1})"

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]  # noqa: D102
		if hasattr(self, "player") and hasattr(self, "team"):
			Notification.objects.create(
				user=self.team.owner,  # pyright: ignore[reportAttributeAccessIssue]
				message=f"{self.player} has signed a contract with your team starting in {self.start_year}",
				priority=1,
				level="info",
			)

		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

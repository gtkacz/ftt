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
		null=True,
		blank=True,
		help_text="Grid-mode weights, kept only for round-trip editing",
	)
	is_active = models.BooleanField(default=False)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="scoring_rules",
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

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # ruff: ignore[undocumented-public-method]
		validate_formula(self.formula_text)
		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

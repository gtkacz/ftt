from collections.abc import Sequence
from typing import Any

from django.db import models

from core.models import Notification, Player


class DraftQueue(models.Model):
	"""Draft queue for a team in a specific draft."""

	team = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="draft_queues")
	draft = models.ForeignKey("Draft", on_delete=models.CASCADE, related_name="team_queues")
	autopick_enabled = models.BooleanField(default=True, help_text="Enable auto-pick from queue")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	queue_items = models.JSONField(
		default=list,
		help_text="List of player IDs in the draft queue",
		blank=True,
		null=True,
		editable=True,
	)

	class Meta:
		unique_together = ("team", "draft")

	def __str__(self) -> str:
		return f"{self.team.name} - {self.draft.year} Draft Queue"

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]  # noqa: D102
		for id_ in self.queue_items:  # pyright: ignore[reportGeneralTypeIssues]
			player = Player.objects.filter(id=id_)

			if not player.exists() or hasattr(player.first(), "contract"):
				self.queue_items.remove(id_)  # pyright: ignore[reportAttributeAccessIssue]  # noqa: B909
				Notification.objects.create(
					user=self.team.owner,
					message=f"Player {player.first()} has been removed from your draft queue because they are no longer available.",
					priority=2,
					level="warning",
				)

		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

	def get_next_player(self) -> Player | None:
		"""Get the next available player from the queue, if any."""  # noqa: DOC201
		if not self.queue_items:
			return None

		return Player.objects.filter(id=self.queue_items[0]).first() if self.queue_items else None

	def remove_player(self, player: Player) -> None:
		"""Remove a player from the queue and reorder."""
		if not self.queue_items:
			return

		queue = self.queue_items

		queue.remove(player.id)  # pyright: ignore[reportAttributeAccessIssue]

		self.queue_items = queue
		self.save()

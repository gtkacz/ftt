"""Trade history model for tracking trade timeline and events.

This module provides an immutable audit log for all trade-related activities,
enabling complete timeline reconstruction and dispute resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
	from core.models.team import Team
	from core.models.trade import Trade
	from core.models.user import User


class TradeHistory(models.Model):
	"""Audit log entry for trade-related events.

	This model maintains an immutable record of all trade activities,
	including creation, modifications, team responses, and commissioner actions.
	Each entry captures the state of the trade at a specific point in time.

	Attributes:
		trade: The trade this event is associated with.
		event_type: Type of event that occurred.
		actor: User who triggered this event (None for system events).
		team: Team involved in this event (if applicable).
		message: Human-readable description or notes.
		assets_snapshot: JSON snapshot of trade assets at this point.
		created_at: When this event occurred.

	Examples:
		>>> trade = Trade.objects.get(pk=1)
		>>> TradeHistory.objects.create(
		...     trade=trade,
		...     event_type="proposed",
		...     actor=user,
		...     message="Trade proposed by Team A"
		... )
	"""

	EVENT_TYPE_CHOICES = [
		("created", "Trade Created"),
		("modified", "Trade Modified"),
		("proposed", "Trade Proposed"),
		("accepted", "Team Accepted"),
		("rejected", "Team Rejected"),
		("countered", "Counter Offer"),
		("cancelled", "Trade Cancelled"),
		("approval_requested", "Approval Requested"),
		("commissioner_voted", "Commissioner Voted"),
		("approved", "Commissioner Approved"),
		("vetoed", "Commissioner Vetoed"),
		("executed", "Trade Executed"),
	]

	trade = models.ForeignKey(
		"Trade",
		on_delete=models.CASCADE,
		related_name="history",
		help_text="The trade this event is for",
	)

	event_type = models.CharField(
		max_length=30,
		choices=EVENT_TYPE_CHOICES,
		help_text="Type of event that occurred",
	)

	actor = models.ForeignKey(
		"User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="trade_actions",
		help_text="User who triggered this event (None for system events)",
	)

	team = models.ForeignKey(
		"Team",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="trade_history",
		help_text="Team involved in this event (if applicable)",
	)

	message = models.TextField(
		blank=True,
		help_text="Human-readable description or notes about this event",
	)

	assets_snapshot = models.JSONField(
		null=True,
		blank=True,
		help_text="JSON snapshot of trade assets at this point in time",
	)

	created_at = models.DateTimeField(
		auto_now_add=True,
		help_text="When this event occurred",
	)

	class Meta:  # noqa: D106
		ordering = ("-created_at",)
		verbose_name = "Trade History"
		verbose_name_plural = "Trade Histories"
		indexes = [
			models.Index(fields=["trade", "-created_at"], name="trade_history_trade_date_idx"),
			models.Index(fields=["event_type"], name="trade_history_event_type_idx"),
			models.Index(fields=["actor"], name="trade_history_actor_idx"),
		]

	def __str__(self) -> str:
		"""Return human-readable string representation.

		Returns:
			String describing the event, actor, and timestamp.

		Examples:
			>>> history = TradeHistory.objects.first()
			>>> str(history)
			'proposed by john_doe at 2025-01-15 14:30:00'
		"""
		actor_name = self.actor.username if self.actor else "System"
		return f"{self.event_type} by {actor_name} at {self.created_at}"

	def __repr__(self) -> str:
		"""Return developer-friendly representation.

		Returns:
			String with class name and key identifiers.

		Examples:
			>>> history = TradeHistory.objects.first()
			>>> repr(history)
			'<TradeHistory(trade_id=1, event=proposed, actor=john_doe)>'
		"""
		actor_name = self.actor.username if self.actor else "System"
		return f"<TradeHistory(trade_id={self.trade_id}, event={self.event_type}, actor={actor_name})>"

	@classmethod
	def create_event(
		cls,
		trade: Trade,
		event_type: str,
		actor: User | None = None,
		team: Team | None = None,
		message: str = "",
		assets_snapshot: dict[str, Any] | None = None,
	) -> TradeHistory:
		"""Create a new history event with validation.

		This is the recommended way to create history entries as it validates
		the event_type and ensures data consistency.

		Args:
			trade: The trade this event is for.
			event_type: Type of event (must be in EVENT_TYPE_CHOICES).
			actor: User who triggered the event (optional).
			team: Team involved in the event (optional).
			message: Description or notes about the event.
			assets_snapshot: JSON-serializable snapshot of assets (optional).

		Returns:
			The created TradeHistory instance.

		Raises:
			ValueError: If event_type is not valid.

		Examples:
			>>> trade = Trade.objects.get(pk=1)
			>>> history = TradeHistory.create_event(
			...     trade=trade,
			...     event_type="proposed",
			...     actor=user,
			...     message="Initial proposal"
			... )
		"""
		valid_types = [choice[0] for choice in cls.EVENT_TYPE_CHOICES]
		if event_type not in valid_types:
			raise ValueError(
				f"Invalid event_type '{event_type}'. Must be one of: {', '.join(valid_types)}"
			)

		return cls.objects.create(
			trade=trade,
			event_type=event_type,
			actor=actor,
			team=team,
			message=message,
			assets_snapshot=assets_snapshot,
		)

	@classmethod
	def get_trade_timeline(cls, trade: Trade) -> models.QuerySet[TradeHistory]:
		"""Get complete chronological timeline for a trade.

		Args:
			trade: The trade to get history for.

		Returns:
			QuerySet of TradeHistory entries ordered by creation time (oldest first).

		Examples:
			>>> trade = Trade.objects.get(pk=1)
			>>> timeline = TradeHistory.get_trade_timeline(trade)
			>>> for event in timeline:
			...     print(f"{event.created_at}: {event.event_type}")
		"""
		return cls.objects.filter(trade=trade).order_by("created_at")

	@classmethod
	def get_recent_events(
		cls,
		trade: Trade,
		limit: int = 10,
	) -> models.QuerySet[TradeHistory]:
		"""Get most recent events for a trade.

		Args:
			trade: The trade to get history for.
			limit: Maximum number of events to return (default: 10).

		Returns:
			QuerySet of most recent TradeHistory entries.

		Examples:
			>>> trade = Trade.objects.get(pk=1)
			>>> recent = TradeHistory.get_recent_events(trade, limit=5)
		"""
		return cls.objects.filter(trade=trade)[:limit]

	def get_actor_display(self) -> str:
		"""Get display name for the actor who triggered this event.

		Returns:
			Username if actor exists, otherwise "System".

		Examples:
			>>> history.get_actor_display()
			'john_doe'
		"""
		return self.actor.username if self.actor else "System"

	def has_snapshot(self) -> bool:
		"""Check if this event includes an assets snapshot.

		Returns:
			True if assets_snapshot is not None, False otherwise.

		Examples:
			>>> history.has_snapshot()
			True
		"""
		return self.assets_snapshot is not None

	def get_snapshot_summary(self) -> str:
		"""Get human-readable summary of the assets snapshot.

		Returns:
			Summary string describing asset counts, or empty string if no snapshot.

		Examples:
			>>> history.get_snapshot_summary()
			'3 players, 2 picks'
		"""
		if not self.has_snapshot():
			return ""

		try:
			assets = self.assets_snapshot
			if not isinstance(assets, list):
				return "Invalid snapshot format"

			player_count = sum(1 for asset in assets if asset.get("asset_type") == "player")
			pick_count = sum(1 for asset in assets if asset.get("asset_type") == "pick")

			parts = []
			if player_count:
				parts.append(f"{player_count} player{'s' if player_count != 1 else ''}")
			if pick_count:
				parts.append(f"{pick_count} pick{'s' if pick_count != 1 else ''}")

			return ", ".join(parts) if parts else "No assets"

		except (AttributeError, TypeError):
			return "Invalid snapshot format"

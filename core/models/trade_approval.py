"""Trade approval model for commissioner voting system.

This module implements a democratic commissioner approval system with
support for majority voting and admin override capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
	from core.models.trade import Trade
	from core.models.user import User


class TradeApproval(models.Model):
	"""Commissioner vote record for trade approval.

	This model tracks individual commissioner votes on trades, enabling
	a democratic approval process with majority rule. Administrators
	(is_superuser=True) can override with instant approval/veto.

	Each commissioner can only vote once per trade, enforced by a
	unique constraint on (trade, commissioner).

	Attributes:
		trade: The trade being voted on.
		commissioner: The commissioner casting this vote.
		vote: Vote decision (approve or veto).
		notes: Optional reasoning or comments.
		voted_at: When the vote was cast.

	Examples:
		>>> trade = Trade.objects.get(pk=1)
		>>> approval = TradeApproval.objects.create(
		...     trade=trade,
		...     commissioner=commissioner_user,
		...     vote="approve",
		...     notes="Fair trade for all parties"
		... )
	"""

	VOTE_CHOICES = [
		("approve", "Approve"),
		("veto", "Veto"),
	]

	trade = models.ForeignKey(
		"Trade",
		on_delete=models.CASCADE,
		related_name="approvals",
		help_text="The trade being voted on",
	)

	commissioner = models.ForeignKey(
		"User",
		on_delete=models.CASCADE,
		related_name="trade_votes",
		help_text="Commissioner casting this vote (must be is_staff or is_superuser)",
	)

	vote = models.CharField(
		max_length=10,
		choices=VOTE_CHOICES,
		help_text="Vote decision: approve or veto",
	)

	notes = models.TextField(
		blank=True,
		help_text="Optional reasoning or comments for the vote",
	)

	voted_at = models.DateTimeField(
		auto_now_add=True,
		help_text="When this vote was cast",
	)

	class Meta:  # noqa: D106
		unique_together = ("trade", "commissioner")
		ordering = ("-voted_at",)
		verbose_name = "Trade Approval"
		verbose_name_plural = "Trade Approvals"
		indexes = [
			models.Index(fields=["trade", "vote"], name="trade_approval_trade_vote_idx"),
			models.Index(fields=["commissioner"], name="trade_approval_comm_idx"),
			models.Index(fields=["-voted_at"], name="trade_approval_date_idx"),
		]

	def __str__(self) -> str:
		"""Return human-readable string representation.

		Returns:
			String describing commissioner, vote, and trade ID.

		Examples:
			>>> approval = TradeApproval.objects.first()
			>>> str(approval)
			'john_doe - Approve on Trade 1'
		"""
		vote_display = self.get_vote_display()  # pyright: ignore[reportAttributeAccessIssue]
		return f"{self.commissioner.username} - {vote_display} on Trade {self.trade_id}"

	def __repr__(self) -> str:
		"""Return developer-friendly representation.

		Returns:
			String with class name and key identifiers.

		Examples:
			>>> approval = TradeApproval.objects.first()
			>>> repr(approval)
			'<TradeApproval(trade_id=1, commissioner=john_doe, vote=approve)>'
		"""
		return (
			f"<TradeApproval(trade_id={self.trade_id}, "
			f"commissioner={self.commissioner.username}, "
			f"vote={self.vote})>"
		)

	def clean(self) -> None:
		"""Validate the approval before saving.

		Validates that:
		- Commissioner has staff or superuser privileges
		- Trade is in appropriate status for voting
		- Vote choice is valid

		Raises:
			ValidationError: If validation fails.

		Examples:
			>>> approval = TradeApproval(trade=trade, commissioner=user, vote="approve")
			>>> approval.clean()  # Raises ValidationError if user is not staff
		"""
		super().clean()

		# Validate commissioner permissions
		if not self.commissioner.is_staff and not self.commissioner.is_superuser:
			raise ValidationError(
				f"User '{self.commissioner.username}' is not a commissioner. "
				"Only users with is_staff=True or is_superuser=True can vote on trades."
			)

		# Validate trade status
		valid_statuses = ["waiting_approval", "accepted"]
		if self.trade.status not in valid_statuses:
			raise ValidationError(
				f"Cannot vote on trade with status '{self.trade.status}'. "
				f"Trade must be in one of: {', '.join(valid_statuses)}"
			)

		# Validate vote choice
		valid_votes = [choice[0] for choice in self.VOTE_CHOICES]
		if self.vote not in valid_votes:
			raise ValidationError(
				f"Invalid vote '{self.vote}'. Must be one of: {', '.join(valid_votes)}"
			)

	def save(self, *args, **kwargs) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Save the approval with full validation.

		Raises:
			ValidationError: If clean() validation fails.

		Examples:
			>>> approval = TradeApproval(trade=trade, commissioner=user, vote="approve")
			>>> approval.save()  # Calls clean() before saving
		"""
		self.full_clean()
		return super().save(*args, **kwargs)

	@classmethod
	def create_vote(
		cls,
		trade: Trade,
		commissioner: User,
		vote: str,
		notes: str = "",
	) -> tuple[TradeApproval, bool]:
		"""Create or update a commissioner vote with validation.

		This is the recommended way to record votes as it handles the
		get_or_create pattern and ensures validation.

		Args:
			trade: The trade being voted on.
			commissioner: The commissioner casting the vote.
			vote: Vote decision ("approve" or "veto").
			notes: Optional reasoning for the vote.

		Returns:
			Tuple of (TradeApproval instance, created boolean).
			created is True if new vote, False if updated existing vote.

		Raises:
			ValidationError: If validation fails (invalid commissioner, status, etc.).

		Examples:
			>>> approval, created = TradeApproval.create_vote(
			...     trade=trade,
			...     commissioner=commissioner_user,
			...     vote="approve",
			...     notes="Looks fair to me"
			... )
			>>> print(f"Vote {'created' if created else 'updated'}")
		"""
		# Create temporary instance for validation
		temp_approval = cls(
			trade=trade,
			commissioner=commissioner,
			vote=vote,
			notes=notes,
		)
		temp_approval.clean()  # Will raise ValidationError if invalid

		# If validation passed, create or update
		approval, created = cls.objects.update_or_create(
			trade=trade,
			commissioner=commissioner,
			defaults={
				"vote": vote,
				"notes": notes,
			},
		)

		return approval, created

	@classmethod
	def get_vote_counts(cls, trade: Trade) -> dict[str, int]:
		"""Get current vote counts for a trade.

		Args:
			trade: The trade to get vote counts for.

		Returns:
			Dictionary with vote counts:
				- approve: Number of approve votes
				- veto: Number of veto votes
				- total: Total number of votes cast

		Examples:
			>>> counts = TradeApproval.get_vote_counts(trade)
			>>> print(f"Approve: {counts['approve']}, Veto: {counts['veto']}")
		"""
		approvals = cls.objects.filter(trade=trade)

		approve_count = approvals.filter(vote="approve").count()
		veto_count = approvals.filter(vote="veto").count()

		return {
			"approve": approve_count,
			"veto": veto_count,
			"total": approve_count + veto_count,
		}

	@classmethod
	def has_voted(cls, trade: Trade, commissioner: User) -> bool:
		"""Check if a commissioner has already voted on a trade.

		Args:
			trade: The trade to check.
			commissioner: The commissioner to check.

		Returns:
			True if commissioner has voted, False otherwise.

		Examples:
			>>> if TradeApproval.has_voted(trade, commissioner):
			...     print("You already voted on this trade")
		"""
		return cls.objects.filter(trade=trade, commissioner=commissioner).exists()

	@classmethod
	def get_pending_voters(cls, trade: Trade) -> models.QuerySet[User]:
		"""Get commissioners who haven't voted yet.

		Args:
			trade: The trade to check.

		Returns:
			QuerySet of User objects who are commissioners but haven't voted.

		Examples:
			>>> pending = TradeApproval.get_pending_voters(trade)
			>>> for commissioner in pending:
			...     print(f"{commissioner.username} hasn't voted yet")
		"""
		from core.models.user import User

		voted_commissioner_ids = cls.objects.filter(trade=trade).values_list(
			"commissioner_id", flat=True
		)

		return User.objects.filter(is_staff=True).exclude(id__in=voted_commissioner_ids)

	def is_admin_vote(self) -> bool:
		"""Check if this vote was cast by an admin (superuser).

		Admin votes can instantly approve/veto trades without requiring
		majority consensus.

		Returns:
			True if commissioner is superuser, False otherwise.

		Examples:
			>>> if approval.is_admin_vote():
			...     print("Admin override - decision is final")
		"""
		return self.commissioner.is_superuser

	def is_approve(self) -> bool:
		"""Check if this is an approval vote.

		Returns:
			True if vote is "approve", False otherwise.

		Examples:
			>>> if approval.is_approve():
			...     print("Commissioner approved the trade")
		"""
		return self.vote == "approve"

	def is_veto(self) -> bool:
		"""Check if this is a veto vote.

		Returns:
			True if vote is "veto", False otherwise.

		Examples:
			>>> if approval.is_veto():
			...     print("Commissioner vetoed the trade")
		"""
		return self.vote == "veto"

	def get_vote_summary(self) -> str:
		"""Get human-readable summary of this vote.

		Returns:
			String summarizing commissioner, vote, and notes if present.

		Examples:
			>>> approval.get_vote_summary()
			'john_doe approved: Fair trade for all teams'
		"""
		verb = "approved" if self.is_approve() else "vetoed"
		base = f"{self.commissioner.username} {verb}"

		if self.notes:
			return f"{base}: {self.notes}"

		return base

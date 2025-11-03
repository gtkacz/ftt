"""Trade models for multi-team fantasy basketball trades.

This module implements a comprehensive trade system supporting:
- Multi-team trades with unlimited participants
- Player and draft pick exchanges
- Pick protections (swap_best, swap_worst, doesnt_convey)
- Commissioner approval workflow with majority voting
- Complete audit trail via TradeHistory
- Salary cap and roster spot validation
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from ftt.settings import LEAGUE_SETTINGS

if TYPE_CHECKING:
	from core.models.team import Team
	from core.models.user import User


class Trade(models.Model):
	"""Model representing a trade between teams in a fantasy league.

	Supports multi-team trades with complete workflow from draft through
	execution, including team negotiations and commissioner approval.

	Status Flow:
		draft → proposed → accepted → waiting_approval → approved → completed
		         └→ rejected               └→ vetoed
		         └→ cancelled

	Attributes:
		proposing_team: Team that initiated the trade.
		teams: All teams involved in the trade.
		status: Current status of the trade.
		created_at: When the trade was created.
		updated_at: When the trade was last modified.
		proposed_at: When the trade was proposed to other teams.
		completed_at: When the trade was executed.
		approved_at: When the trade was approved by commissioner.
		approved_by: Commissioner who approved the trade.
		notes: Optional notes about the trade.

	Examples:
		>>> trade = Trade.objects.create(
		...     proposing_team=team_a,
		...     status="draft"
		... )
		>>> trade.teams.set([team_a, team_b, team_c])
		>>> trade.propose()
	"""

	STATUS_CHOICES = [
		("draft", "Draft"),  # Being composed
		("proposed", "Proposed"),  # Sent to other teams
		("accepted", "Accepted"),  # All teams accepted (deprecated)
		("rejected", "Rejected"),  # At least one team rejected
		("cancelled", "Cancelled"),  # Cancelled by proposer
		("waiting_approval", "Waiting for Approval"),  # Needs commissioner approval
		("approved", "Approved"),  # Commissioner approved
		("completed", "Completed"),  # Trade has been executed
		("vetoed", "Vetoed"),  # Commissioner vetoed
	]

	# The team that initiated the trade
	proposing_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="proposed_trades",
		help_text="Team that proposed this trade",
	)

	# All teams involved in the trade (including proposer)
	teams = models.ManyToManyField(
		"Team",
		related_name="trades",
		help_text="All teams involved in the trade",
	)

	status = models.CharField(
		max_length=20,
		choices=STATUS_CHOICES,
		default="draft",
		help_text="Current status of the trade",
	)

	# Timestamps
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	proposed_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was proposed to other teams",
	)
	completed_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was executed",
	)
	approved_at = models.DateTimeField(
		blank=True,
		null=True,
		help_text="When the trade was approved by commissioner",
	)

	# Commissioner approval tracking
	approved_by = models.ForeignKey(
		"User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="approved_trades",
		help_text="Commissioner who approved the trade",
	)

	# Notes/messages
	notes = models.TextField(
		blank=True,
		help_text="Optional notes about the trade",
	)

	class Meta:  # noqa: D106
		ordering = ("-created_at",)
		indexes = [
			models.Index(fields=["status"]),
			models.Index(fields=["proposing_team", "status"]),
			models.Index(fields=["-created_at"]),
		]

	def __str__(self) -> str:
		"""Return human-readable string representation.

		Returns:
			String with trade ID, teams, and status.

		Examples:
			>>> str(trade)
			'Trade 1 (Lakers, Celtics, Warriors) - Proposed'
		"""
		team_names = ", ".join(str(team) for team in self.teams.all()[:3])
		return f"Trade {self.id} ({team_names}) - {self.get_status_display()}"  # pyright: ignore[reportAttributeAccessIssue]

	def clean(self) -> None:
		"""Validate the trade before saving.

		Validates salary cap and roster compliance for all teams when
		trade is being accepted, approved, or completed.

		Raises:
			ValidationError: If validation fails.
		"""
		super().clean()

		# Only validate when moving to accepted/approved status
		if self.status in ["accepted", "approved", "completed", "waiting_approval"]:
			# Check cap compliance for all teams
			for team in self.teams.all():
				try:
					self._validate_team_caps(team)
				except ValidationError as e:
					raise ValidationError(f"Trade invalid for {team.name}: {e.message}") from e

			# Validate all traded players
			for asset in self.assets.filter(asset_type="player"):
				self._validate_player_tradeable(asset)

	def _validate_team_caps(self, team: Team) -> None:
		"""Validate that team won't exceed caps after trade.

		Args:
			team: Team to validate.

		Raises:
			ValidationError: If team would exceed salary or roster cap.
		"""
		incoming_salary = sum(
			asset.player.contract.salary
			for asset in self.assets.filter(receiving_team=team, asset_type="player")
			if asset.player and hasattr(asset.player, "contract")
		)
		outgoing_salary = sum(
			asset.player.contract.salary
			for asset in self.assets.filter(giving_team=team, asset_type="player")
			if asset.player and hasattr(asset.player, "contract")
		)

		incoming_players = self.assets.filter(receiving_team=team, asset_type="player").count()
		outgoing_players = self.assets.filter(giving_team=team, asset_type="player").count()

		net_salary = incoming_salary - outgoing_salary
		net_players = incoming_players - outgoing_players

		# Check salary cap
		if team.total_salary() + net_salary > LEAGUE_SETTINGS.SALARY_CAP:
			raise ValidationError(
				f"{team.name} would exceed salary cap. "
				f"Current: {team.total_salary()}, Net change: {net_salary}, "
				f"Cap: {LEAGUE_SETTINGS.SALARY_CAP}"
			)

		# Check player cap
		if team.total_players() + net_players > LEAGUE_SETTINGS.MAX_PLAYER_CAP:
			raise ValidationError(
				f"{team.name} would exceed player cap. "
				f"Current: {team.total_players()}, Net change: {net_players}, "
				f"Cap: {LEAGUE_SETTINGS.MAX_PLAYER_CAP}"
			)

	def _validate_player_tradeable(self, asset: TradeAsset) -> None:
		"""Validate that a player can be traded.

		Args:
			asset: Trade asset to validate.

		Raises:
			ValidationError: If player cannot be traded.
		"""
		if not asset.player:
			return

		player = asset.player
		giving_team = asset.giving_team

		# Check if player has a contract
		if not hasattr(player, "contract"):
			raise ValidationError(f"{player} has no contract and cannot be traded")

		contract = player.contract

		# Validate the giving team owns the player's rights
		if contract.team != giving_team:
			# Special case: RFA players can be traded by rights owner
			if not contract.is_rfa:
				raise ValidationError(f"{player} is not owned by {giving_team.name}")

			# For RFA, check if giving_team owns the rights
			if contract.team != giving_team:
				raise ValidationError(f"{giving_team.name} does not own rights to RFA {player}")

		# Check if player is RFA-only (0 years left)
		current_year = timezone.now().year
		years_remaining = (contract.start_year + contract.duration) - current_year

		if years_remaining <= 0 and not contract.is_rfa:
			raise ValidationError(
				f"{player} has {years_remaining} years remaining and is not an RFA. "
				"Only RFA players with 0 years can be traded."
			)

	# Helper Methods for Notifications and History

	def _create_notification(
		self,
		users: list[User],
		message: str,
		level: str = "info",
		priority: int = 1,
	) -> None:
		"""Create notifications for multiple users.

		Args:
			users: List of User objects to notify.
			message: Notification message.
			level: Notification level (info, warning, error).
			priority: Priority level (1-10, higher is more important).

		Examples:
			>>> trade._create_notification(
			...     users=[user1, user2],
			...     message="Trade proposal received",
			...     level="info",
			...     priority=5
			... )
		"""
		from core.models import Notification

		for user in users:
			Notification.objects.create(
				user=user,
				message=message,
				level=level,
				priority=priority,
			)

	def _log_event(
		self,
		event_type: str,
		actor: User | None = None,
		team: Team | None = None,
		message: str = "",
		include_assets: bool = False,
	) -> None:
		"""Log event to trade history.

		Creates an immutable audit log entry for the trade event.

		Args:
			event_type: Type of event (see TradeHistory.EVENT_TYPE_CHOICES).
			actor: User who triggered the event (None for system events).
			team: Team involved in event (optional).
			message: Description or notes about the event.
			include_assets: Whether to snapshot current assets.

		Examples:
			>>> trade._log_event(
			...     event_type="proposed",
			...     actor=user,
			...     team=team,
			...     message="Trade proposed by Team A",
			...     include_assets=True
			... )
		"""
		from core.models import TradeHistory
		from core.serializers import TradeAssetSerializer

		snapshot = None
		if include_assets:
			# Create JSON snapshot of current assets
			assets = self.assets.all()
			snapshot = TradeAssetSerializer(assets, many=True).data

		TradeHistory.objects.create(
			trade=self,
			event_type=event_type,
			actor=actor,
			team=team,
			message=message,
			assets_snapshot=snapshot,
		)

	def _get_all_team_owners(self) -> list[User]:
		"""Get all team owners involved in the trade.

		Returns:
			List of User objects who own teams in this trade.

		Examples:
			>>> owners = trade._get_all_team_owners()
			>>> len(owners)
			3
		"""
		return [team.owner for team in self.teams.all()]

	def _get_all_commissioners(self) -> list[User]:
		"""Get all commissioners (staff users).

		Returns:
			List of User objects with is_staff=True.

		Examples:
			>>> commissioners = trade._get_all_commissioners()
			>>> all(c.is_staff for c in commissioners)
			True
		"""
		from core.models import User

		return list(User.objects.filter(is_staff=True))

	# Trade Workflow Methods

	@transaction.atomic
	def propose(self) -> None:
		"""Propose the trade to all involved teams.

		Changes status from draft to proposed, creates TradeOffer objects
		for all teams, logs the event, and notifies all parties.

		Raises:
			ValidationError: If trade is not in draft status.

		Examples:
			>>> trade = Trade.objects.create(proposing_team=team_a, status="draft")
			>>> trade.teams.set([team_a, team_b])
			>>> trade.propose()
			>>> trade.status
			'proposed'
		"""
		if self.status != "draft":
			raise ValidationError(f"Cannot propose trade with status {self.status}")

		self.status = "proposed"
		self.proposed_at = timezone.now()
		self.save()

		# Create initial offer for all teams
		for team in self.teams.all():
			TradeOffer.objects.create(
				trade=self,
				team=team,
				is_proposer=(team == self.proposing_team),
				status="accepted" if team == self.proposing_team else "pending",
			)

		# Log the proposal event
		self._log_event(
			event_type="proposed",
			actor=self.proposing_team.owner,
			team=self.proposing_team,
			message=f"Trade proposed by {self.proposing_team.name}",
			include_assets=True,  # Snapshot the proposed assets
		)

		# Notify all non-proposing team owners
		other_owners = [team.owner for team in self.teams.all() if team != self.proposing_team]

		team_names = ", ".join(team.name for team in self.teams.all())

		self._create_notification(
			users=other_owners,
			message=f"New trade proposal from {self.proposing_team.name} involving: {team_names}",
			level="info",
			priority=5,  # Trade proposals are important
		)

		# Notify proposer that trade was sent
		self._create_notification(
			users=[self.proposing_team.owner],
			message=f"Your trade proposal has been sent to {len(other_owners)} team(s)",
			level="info",
			priority=3,
		)

	@transaction.atomic
	def request_approval(self) -> None:
		"""Request commissioner approval after all teams accept.

		Called automatically when all teams have accepted. If no commissioners
		exist, auto-approves the trade. Otherwise, sets status to waiting_approval
		and notifies all commissioners.

		Examples:
			>>> trade.request_approval()
			>>> trade.status
			'waiting_approval'
		"""
		from core.models import User

		commissioners = self._get_all_commissioners()

		if not commissioners:
			# No commissioners - auto-approve
			self.status = "approved"
			self.approved_at = timezone.now()
			self.save()

			self._log_event(
				event_type="approved",
				message="Auto-approved (no commissioners)",
			)

			# Notify teams
			self._create_notification(
				users=self._get_all_team_owners(),
				message="Trade approved (no commissioner review required)",
				level="info",
				priority=8,
			)
			return

		# Has commissioners - request approval
		self.status = "waiting_approval"
		self.save()

		self._log_event(
			event_type="approval_requested",
			message=f"Awaiting approval from {len(commissioners)} commissioner(s)",
		)

		# Notify commissioners
		team_names = ", ".join(team.name for team in self.teams.all())

		self._create_notification(
			users=commissioners,
			message=f"Trade between {team_names} requires approval",
			level="info",
			priority=10,  # Highest priority for commissioners
		)

		# Notify teams
		self._create_notification(
			users=self._get_all_team_owners(),
			message="Trade sent to commissioners for approval",
			level="info",
			priority=6,
		)

	@transaction.atomic
	def record_commissioner_vote(
		self,
		commissioner: User,
		vote: str,
		notes: str = "",
	) -> dict[str, Any]:
		"""Record a commissioner vote and check if decision threshold reached.

		Handles both regular commissioner votes (majority required) and
		admin overrides (instant decision).

		Args:
			commissioner: User casting the vote (must be is_staff or is_superuser).
			vote: Vote decision ("approve" or "veto").
			notes: Optional reasoning for the vote.

		Returns:
			Dictionary with:
				- decision_made: bool (whether threshold reached)
				- final_status: str (current trade status)
				- votes_needed: int (votes remaining for decision, 0 if decided)

		Raises:
			ValidationError: If commissioner lacks permissions or trade in wrong status.

		Examples:
			>>> result = trade.record_commissioner_vote(
			...     commissioner=admin_user,
			...     vote="approve",
			...     notes="Fair trade"
			... )
			>>> result['decision_made']
			True
		"""
		from core.models import TradeApproval, User

		# Validation
		if not commissioner.is_staff and not commissioner.is_superuser:
			raise ValidationError(f"{commissioner.username} is not a commissioner")

		if self.status != "waiting_approval":
			raise ValidationError(f"Trade status is {self.status}, not waiting_approval")

		# Admin override - instant decision
		if commissioner.is_superuser:
			if vote == "approve":
				self.status = "approved"
				self.approved_at = timezone.now()
				self.approved_by = commissioner
			else:
				self.status = "vetoed"

			self.save()

			# Create approval record
			TradeApproval.objects.create(
				trade=self,
				commissioner=commissioner,
				vote=vote,
				notes=notes or "Admin override",
			)

			# Log event
			self._log_event(
				event_type="approved" if vote == "approve" else "vetoed",
				actor=commissioner,
				message=f"Admin {commissioner.username} {vote}d the trade: {notes}",
			)

			# Notify everyone
			final_status = "approved" if vote == "approve" else "vetoed"

			self._create_notification(
				users=self._get_all_team_owners(),
				message=f"Trade {final_status} by admin {commissioner.username}",
				level="info" if vote == "approve" else "warning",
				priority=10,
			)

			# Notify other commissioners
			other_commissioners = [c for c in self._get_all_commissioners() if c != commissioner]
			self._create_notification(
				users=other_commissioners,
				message=f"Trade {final_status} by admin {commissioner.username}",
				level="info",
				priority=8,
			)

			return {"decision_made": True, "final_status": self.status, "votes_needed": 0}

		# Regular commissioner vote
		approval, created = TradeApproval.objects.update_or_create(
			trade=self,
			commissioner=commissioner,
			defaults={"vote": vote, "notes": notes},
		)

		# Log the vote
		self._log_event(
			event_type="commissioner_voted",
			actor=commissioner,
			message=f"Commissioner {commissioner.username} voted {vote}: {notes}",
		)

		# Check if majority reached
		total_commissioners = User.objects.filter(is_staff=True).count()
		approve_count = self.approvals.filter(vote="approve").count()
		veto_count = self.approvals.filter(vote="veto").count()
		majority_needed = (total_commissioners // 2) + 1

		# Majority approve
		if approve_count >= majority_needed:
			self.status = "approved"
			self.approved_at = timezone.now()
			self.approved_by = commissioner  # Last vote that triggered approval
			self.save()

			self._log_event(
				event_type="approved",
				message=f"Approved by commissioner majority ({approve_count}/{total_commissioners})",
			)

			self._create_notification(
				users=self._get_all_team_owners(),
				message=f"Trade approved by commissioner vote ({approve_count}/{total_commissioners})",
				level="info",
				priority=10,
			)

			return {"decision_made": True, "final_status": "approved", "votes_needed": 0}

		# Majority veto
		if veto_count >= majority_needed:
			self.status = "vetoed"
			self.save()

			self._log_event(
				event_type="vetoed",
				message=f"Vetoed by commissioner majority ({veto_count}/{total_commissioners})",
			)

			self._create_notification(
				users=self._get_all_team_owners(),
				message=f"Trade vetoed by commissioner vote ({veto_count}/{total_commissioners})",
				level="warning",
				priority=10,
			)

			return {"decision_made": True, "final_status": "vetoed", "votes_needed": 0}

		# No decision yet - notify commissioners who haven't voted
		voted_commissioner_ids = self.approvals.values_list("commissioner_id", flat=True)
		pending_commissioners = User.objects.filter(is_staff=True).exclude(id__in=voted_commissioner_ids)

		if pending_commissioners.exists():
			votes_needed = majority_needed - max(approve_count, veto_count)

			self._create_notification(
				users=list(pending_commissioners),
				message=f"Trade needs {votes_needed} more vote(s). Current: {approve_count} approve, {veto_count} veto",
				level="info",
				priority=9,
			)

		return {
			"decision_made": False,
			"final_status": self.status,
			"votes_needed": majority_needed - max(approve_count, veto_count),
		}

	@transaction.atomic
	def execute(self) -> None:
		"""Execute the trade by transferring assets between teams.

		Transfers players and picks between teams, applies pick protections,
		updates status to completed, logs the event, and notifies all parties.

		Raises:
			ValidationError: If trade is not in approved status or validation fails.

		Examples:
			>>> trade.execute()
			>>> trade.status
			'completed'
		"""
		if self.status not in ["accepted", "approved"]:
			raise ValidationError(f"Cannot execute trade with status {self.status}")

		# Perform full clean before execution
		self.full_clean()

		# Transfer players
		for asset in self.assets.filter(asset_type="player"):
			if asset.player and hasattr(asset.player, "contract"):
				asset.player.contract.team = asset.receiving_team
				asset.player.contract.save()

		# Transfer picks
		for asset in self.assets.filter(asset_type="pick"):
			if asset.pick:
				asset.pick.current_team = asset.receiving_team

				# Apply protections if specified in the trade
				if asset.pick_protection_type and asset.pick_protection_type != "none":
					asset.pick.protection_type = asset.pick_protection_type

					if asset.pick_protection_type == "doesnt_convey":
						asset.pick.protection_range_start = asset.pick_protection_range_start
						asset.pick.protection_range_end = asset.pick_protection_range_end
						asset.pick.rollover_year = asset.pick_rollover_year

					elif asset.pick_protection_type in ["swap_best", "swap_worst"]:
						asset.pick.swap_target_pick = asset.pick_swap_target

				asset.pick.save()

		# Update trade status
		self.status = "completed"
		self.completed_at = timezone.now()
		self.save()

		# Log execution
		self._log_event(
			event_type="executed",
			message="Trade successfully executed",
			include_assets=True,  # Final snapshot
		)

		# Notify all teams
		self._create_notification(
			users=self._get_all_team_owners(),
			message="Trade completed! Check your roster for changes.",
			level="info",
			priority=10,
		)

	# Utility Methods

	def get_team_assets(self, team: Team) -> dict[str, Any]:
		"""Get all assets being given and received by a specific team.

		Args:
			team: Team to get assets for.

		Returns:
			Dictionary with 'giving' and 'receiving' keys, each containing
			'players' and 'picks' lists.

		Examples:
			>>> assets = trade.get_team_assets(team)
			>>> len(assets['giving']['players'])
			2
			>>> len(assets['receiving']['picks'])
			1
		"""
		return {
			"giving": {
				"players": list(self.assets.filter(giving_team=team, asset_type="player").select_related("player")),
				"picks": list(self.assets.filter(giving_team=team, asset_type="pick").select_related("pick")),
			},
			"receiving": {
				"players": list(
					self.assets.filter(receiving_team=team, asset_type="player").select_related("player")
				),
				"picks": list(self.assets.filter(receiving_team=team, asset_type="pick").select_related("pick")),
			},
		}

	def all_teams_accepted(self) -> bool:
		"""Check if all teams have accepted the trade.

		Returns:
			True if all teams have accepted, False otherwise.

		Examples:
			>>> trade.all_teams_accepted()
			True
		"""
		total_teams = self.teams.count()
		accepted_offers = self.offers.filter(status="accepted").count()
		return total_teams > 0 and accepted_offers == total_teams


class TradeOffer(models.Model):
	"""Model representing a team's response to a trade offer.

	Tracks individual team responses (accept, reject, counter) to trade
	proposals and maintains negotiation history.

	Attributes:
		trade: The trade this offer is for.
		team: Team making this response.
		status: Status of this team's response.
		is_proposer: Whether this team proposed the trade.
		counter_offer: Link to offer this counters (if applicable).
		message: Optional message with the response.
		created_at: When this offer was created.
		updated_at: When this offer was last modified.
		responded_at: When the team responded to the offer.

	Examples:
		>>> offer = TradeOffer.objects.get(team=team, trade=trade)
		>>> offer.accept(message="Great trade!")
	"""

	STATUS_CHOICES = [
		("pending", "Pending"),
		("accepted", "Accepted"),
		("rejected", "Rejected"),
		("countered", "Countered"),
	]

	trade = models.ForeignKey(
		Trade,
		on_delete=models.CASCADE,
		related_name="offers",
		help_text="The trade this offer is for",
	)

	team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="trade_offers",
		help_text="Team making this offer/response",
	)

	status = models.CharField(
		max_length=20,
		choices=STATUS_CHOICES,
		default="pending",
		help_text="Status of this team's response",
	)

	is_proposer = models.BooleanField(
		default=False,
		help_text="Whether this team proposed the trade",
	)

	# Counter-offer tracking
	counter_offer = models.ForeignKey(
		"self",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="original_offer",
		help_text="If this is a counter-offer, reference to the offer it counters",
	)

	message = models.TextField(
		blank=True,
		help_text="Optional message with the offer",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	responded_at = models.DateTimeField(
		null=True,
		blank=True,
		help_text="When the team responded to the offer",
	)

	class Meta:  # noqa: D106
		ordering = ("-created_at",)
		indexes = [
			models.Index(fields=["trade", "team"]),
			models.Index(fields=["status"]),
		]

	def __str__(self) -> str:
		"""Return human-readable string representation.

		Returns:
			String with team, status, and trade ID.

		Examples:
			>>> str(offer)
			'Lakers - Accepted for Trade 1'
		"""
		return f"{self.team} - {self.get_status_display()} for Trade {self.trade_id}"  # pyright: ignore[reportAttributeAccessIssue]

	@transaction.atomic
	def accept(self, message: str = "") -> None:
		"""Accept the trade offer.

		Marks this offer as accepted, logs the event, notifies other teams,
		and triggers approval workflow if all teams have accepted.

		Args:
			message: Optional message explaining acceptance.

		Examples:
			>>> offer.accept(message="Good deal for both sides")
			>>> offer.status
			'accepted'
		"""
		self.status = "accepted"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Log acceptance
		self.trade._log_event(
			event_type="accepted",
			actor=self.team.owner,
			team=self.team,
			message=message or f"{self.team.name} accepted the trade",
		)

		# Notify other teams
		other_owners = [t.owner for t in self.trade.teams.all() if t != self.team]

		self.trade._create_notification(
			users=other_owners,
			message=f"{self.team.name} accepted the trade proposal",
			level="info",
			priority=5,
		)

		# Check if all teams accepted
		if self.trade.all_teams_accepted():
			# Request commissioner approval
			self.trade.request_approval()

	@transaction.atomic
	def reject(self, message: str = "") -> None:
		"""Reject the trade offer.

		Marks this offer as rejected, updates trade status to rejected,
		logs the event, and notifies all teams.

		Args:
			message: Optional message explaining rejection.

		Examples:
			>>> offer.reject(message="Not enough value for our team")
			>>> offer.status
			'rejected'
		"""
		self.status = "rejected"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Update trade status
		self.trade.status = "rejected"
		self.trade.save()

		# Log rejection
		self.trade._log_event(
			event_type="rejected",
			actor=self.team.owner,
			team=self.team,
			message=message or f"{self.team.name} rejected the trade",
		)

		# Notify all teams
		all_owners = self.trade._get_all_team_owners()

		self.trade._create_notification(
			users=all_owners,
			message=f"{self.team.name} rejected the trade proposal" + (f": {message}" if message else ""),
			level="warning",
			priority=5,
		)

	@transaction.atomic
	def counter(self, message: str = "") -> Trade:
		"""Create a counter-offer (new trade based on this one).

		Marks this offer as countered, creates a new trade in draft status,
		logs events on both trades, and notifies all teams.

		Args:
			message: Optional message explaining counter-offer.

		Returns:
			The newly created counter-offer trade.

		Examples:
			>>> new_trade = offer.counter(message="How about we swap picks too?")
			>>> new_trade.proposing_team == offer.team
			True
		"""
		# Mark this offer as countered
		self.status = "countered"
		self.message = message
		self.responded_at = timezone.now()
		self.save()

		# Create new trade as counter-offer
		new_trade = Trade.objects.create(
			proposing_team=self.team,
			status="draft",
			notes=f"Counter-offer to Trade {self.trade_id}",
		)

		# Copy teams
		new_trade.teams.set(self.trade.teams.all())

		# Create counter-offer link
		TradeOffer.objects.create(
			trade=new_trade,
			team=self.team,
			is_proposer=True,
			counter_offer=self,
			status="accepted",
		)

		# Log counter on original trade
		self.trade._log_event(
			event_type="countered",
			actor=self.team.owner,
			team=self.team,
			message=f"{self.team.name} countered with Trade #{new_trade.id}",
		)

		# Log creation on new trade
		new_trade._log_event(
			event_type="created",
			actor=self.team.owner,
			team=self.team,
			message=f"Counter-offer to Trade #{self.trade_id}",
			include_assets=True,
		)

		# Notify all teams
		all_owners = self.trade._get_all_team_owners()

		self.trade._create_notification(
			users=all_owners,
			message=f"{self.team.name} sent a counter-offer (Trade #{new_trade.id})",
			level="info",
			priority=5,
		)

		return new_trade


class TradeAsset(models.Model):
	"""Model representing an asset (player or pick) being traded.

	Tracks individual assets in a trade, including players and draft picks
	with optional protections.

	Attributes:
		trade: The trade this asset is part of.
		asset_type: Type of asset (player or pick).
		giving_team: Team giving up this asset.
		receiving_team: Team receiving this asset.
		player: Player being traded (if asset_type is 'player').
		pick: Pick being traded (if asset_type is 'pick').
		pick_protection_type: Type of protection on traded pick.
		pick_protection_range_start: Start of protected range for doesnt_convey.
		pick_protection_range_end: End of protected range for doesnt_convey.
		pick_swap_target: Pick to swap with for swap_best/swap_worst.
		pick_rollover_year: Year to roll over to if pick doesn't convey.
		created_at: When this asset was added to the trade.

	Examples:
		>>> asset = TradeAsset.objects.create(
		...     trade=trade,
		...     asset_type="player",
		...     giving_team=team_a,
		...     receiving_team=team_b,
		...     player=player
		... )
	"""

	ASSET_TYPE_CHOICES = [
		("player", "Player"),
		("pick", "Pick"),
	]

	trade = models.ForeignKey(
		Trade,
		on_delete=models.CASCADE,
		related_name="assets",
		help_text="The trade this asset is part of",
	)

	asset_type = models.CharField(
		max_length=10,
		choices=ASSET_TYPE_CHOICES,
		help_text="Type of asset being traded",
	)

	# Team giving the asset
	giving_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="assets_given",
		help_text="Team giving up this asset",
	)

	# Team receiving the asset
	receiving_team = models.ForeignKey(
		"Team",
		on_delete=models.CASCADE,
		related_name="assets_received",
		help_text="Team receiving this asset",
	)

	# Asset references (only one should be set based on asset_type)
	player = models.ForeignKey(
		"Player",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="trade_assets",
		help_text="Player being traded (if asset_type is 'player')",
	)

	pick = models.ForeignKey(
		"draft.Pick",
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="trade_assets",
		help_text="Pick being traded (if asset_type is 'pick')",
	)

	# Pick-specific protection fields
	pick_protection_type = models.CharField(
		max_length=20,
		blank=True,
		default="none",
		help_text="Type of protection on traded pick (none, swap_best, swap_worst, doesnt_convey)",
	)

	pick_protection_range_start = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Start of protected range for doesnt_convey (e.g., 1 for top-5)",
	)

	pick_protection_range_end = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="End of protected range for doesnt_convey (e.g., 5 for top-5)",
	)

	pick_swap_target = models.ForeignKey(
		"draft.Pick",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="swap_trade_assets",
		help_text="Pick to swap with for swap_best/swap_worst",
	)

	pick_rollover_year = models.PositiveIntegerField(
		null=True,
		blank=True,
		help_text="Year to roll over to if pick doesn't convey",
	)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:  # noqa: D106
		ordering = ("asset_type", "created_at")
		indexes = [
			models.Index(fields=["trade", "asset_type"]),
			models.Index(fields=["giving_team"]),
			models.Index(fields=["receiving_team"]),
		]

	def __str__(self) -> str:
		"""Return human-readable string representation.

		Returns:
			String describing the asset transfer and protections.

		Examples:
			>>> str(asset)
			'LeBron James from Lakers to Celtics'
		"""
		if self.asset_type == "player" and self.player:
			return f"{self.player} from {self.giving_team} to {self.receiving_team}"
		elif self.asset_type == "pick" and self.pick:
			protection = self._get_protection_display()
			return f"{self.pick} from {self.giving_team} to {self.receiving_team}{protection}"
		return f"Unknown asset from {self.giving_team} to {self.receiving_team}"

	def _get_protection_display(self) -> str:
		"""Generate protection display string for pick trades.

		Returns:
			Human-readable protection description.

		Examples:
			>>> asset._get_protection_display()
			" (Doesn't convey picks 1-5)"
		"""
		if self.pick_protection_type == "none" or not self.pick_protection_type:
			return ""

		if self.pick_protection_type == "doesnt_convey":
			if self.pick_protection_range_start and self.pick_protection_range_end:
				return f" (Doesn't convey picks {self.pick_protection_range_start}-{self.pick_protection_range_end})"
			return " (Doesn't convey - protected)"

		if self.pick_protection_type == "swap_best" and self.pick_swap_target:
			return f" (Swap to best with {self.pick_swap_target.original_team.name})"

		if self.pick_protection_type == "swap_worst" and self.pick_swap_target:
			return f" (Swap to worst with {self.pick_swap_target.original_team.name})"

		return f" ({self.pick_protection_type})"

	def clean(self) -> None:
		"""Validate the asset.

		Validates that correct asset is set, protections are valid, etc.

		Raises:
			ValidationError: If validation fails.
		"""
		super().clean()

		# Validate that the correct asset is set
		if self.asset_type == "player" and not self.player:
			raise ValidationError("Player must be set when asset_type is 'player'")
		if self.asset_type == "pick" and not self.pick:
			raise ValidationError("Pick must be set when asset_type is 'pick'")

		# Validate that only one asset is set
		if self.player and self.pick:
			raise ValidationError("Cannot have both player and pick set")

		# Validate pick protections
		if self.asset_type == "pick" and self.pick_protection_type != "none":
			if self.pick_protection_type in ["swap_best", "swap_worst"]:
				if not self.pick_swap_target:
					raise ValidationError(
						f"pick_swap_target required for protection type '{self.pick_protection_type}'"
					)

				if self.pick_swap_target == self.pick:
					raise ValidationError("Cannot swap pick with itself")

			if self.pick_protection_type == "doesnt_convey":
				if not self.pick_protection_range_start or not self.pick_protection_range_end:
					raise ValidationError(
						"pick_protection_range_start and pick_protection_range_end required for doesnt_convey"
					)

				if self.pick_protection_range_start > self.pick_protection_range_end:
					raise ValidationError("pick_protection_range_start must be <= pick_protection_range_end")

				if not self.pick_rollover_year:
					raise ValidationError("pick_rollover_year required for doesnt_convey protection")

				if self.pick and self.pick_rollover_year <= self.pick.draft_year:
					raise ValidationError("pick_rollover_year must be after pick's draft_year")

	def save(self, *args: Sequence[Any], **kwargs: dict[str, Any]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Save the asset with validation.

		Raises:
			ValidationError: If validation fails.
		"""
		self.full_clean()
		return super().save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

from django.core.exceptions import ValidationError
from django.db import models, transaction

from core.models import Contract
from draft.models import Pick


class TradeAsset(models.Model):
	"""A tradeable asset (player contract or draft pick) in the league."""

	sender = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="trade_assets")
	receiver = models.ForeignKey("core.Team", on_delete=models.CASCADE, related_name="received_trade_assets")
	trade = models.ForeignKey("trade.Trade", on_delete=models.CASCADE, related_name="assets")
	asset_type = models.CharField(max_length=20, choices=[("player", "Player"), ("pick", "Draft Pick")])
	player_contract = models.ForeignKey(
		Contract,
		null=True,
		blank=True,
		on_delete=models.CASCADE,
		related_name="trade_assets",
	)
	draft_pick = models.ForeignKey(Pick, null=True, blank=True, on_delete=models.CASCADE, related_name="trade_assets")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:  # noqa: D106
		ordering = ("created_at", "updated_at")
		indexes = (models.Index(fields=["sender", "receiver"]), models.Index(fields=["trade"]))

	def __str__(self) -> str:
		return f"TradeAsset ({self.asset_type}) from {self.sender.name} to {self.receiver.name}"

	@property
	def asset(self) -> models.Model:
		"""
		The underlying asset (player contract or draft pick).

		Raises:
			ValidationError: Unknown asset type.

		Returns:
			models.Model: The asset.
		"""
		if self.asset_type == "player":
			return self.player_contract

		if self.asset_type == "pick":
			return self.draft_pick

		raise ValidationError("Unknown asset type.")

	@transaction.atomic
	def transfer_asset(self) -> None:
		"""
		Executes the trade by transferring the asset to the receiver.

		Raises:
			ValidationError: If the asset type is unknown.
		"""
		if self.asset_type == "player":
			self.player_contract.team = self.receiver
			self.player_contract.save()

		elif self.asset_type == "pick":
			self.draft_pick.current_team = self.receiver
			self.draft_pick.save()

		else:
			raise ValidationError("Unknown asset type.")

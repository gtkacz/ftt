from typing import TYPE_CHECKING

from django.db.transaction import atomic
from rest_framework import mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from core.models import Contract, Team
from draft.models import Pick
from trade.models import Trade, TradeAsset
from trade.serializers.trade import TradeSerializer

if TYPE_CHECKING:
	from trade.types.asset_payload import AssetPayload


class TradeViewSet(
	mixins.CreateModelMixin,
	mixins.RetrieveModelMixin,
	mixins.UpdateModelMixin,
	mixins.DestroyModelMixin,
	mixins.ListModelMixin,
	GenericViewSet,
):
	"""
	A viewset for viewing and editing trade instances.
	"""

	serializer_class = TradeSerializer
	permission_classes = (IsAuthenticated,)

	def get_queryset(self) -> Trade:
		"""Restrict trades to those involving the authenticated user's team."""
		user = self.request.user
		queryset = Trade.objects.all()

		if not user.is_staff and not user.is_superuser:
			queryset = queryset.filter(participants__owner=user).distinct()

		return queryset

	def create(self, request: Request, *args, **kwargs) -> Response:
		"""Override create to create the underlying trade assets."""
		assets_data: list[AssetPayload] = request.data

		# We need to transform the payload to just have `sender` `participants`
		sender = Team.objects.get(owner=request.user)

		with atomic():
			# First create the Trade object
			trade = Trade(sender=sender)
			trade.save()
			trade.participants.set([*list({asset["receiver"] for asset in assets_data}), sender])

			# Then create the TradeAsset objects associated with the Trade
			for asset_data in assets_data:
				curr_receiver_id = asset_data["receiver"]
				player_assets = asset_data["assets"]["players"]
				pick_assets = asset_data["assets"]["picks"]

				for player_contract_id in player_assets:
					TradeAsset.objects.create(
						trade=trade,
						sender=Contract.objects.get(id=player_contract_id).team,
						receiver_id=curr_receiver_id,
						asset_type="player",
						player_contract_id=player_contract_id,
					)

				for pick in pick_assets:
					pick_id = pick["id"]
					pick_protection = pick.get("protection", "unprotected")

					curr_pick = Pick.objects.get(id=pick_id)
					curr_pick.protection = pick_protection
					curr_pick.save()

					TradeAsset.objects.create(
						trade=trade,
						sender=curr_pick.current_team,
						receiver_id=curr_receiver_id,
						asset_type="pick",
						draft_pick_id=pick_id,
					)

			trade.handle_changes()
			trade.validate_compliance()

		return Response({"status": f"Trade created successfully: {trade}"}, status=status.HTTP_201_CREATED)

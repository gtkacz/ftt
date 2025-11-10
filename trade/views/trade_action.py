from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Team
from trade.enums.trade_statuses import TradeStatuses
from trade.models import Trade


class TradeActionView(APIView):
	"""View to handle trade actions like accept, reject, and counteroffer."""

	permission_classes = (IsAuthenticated,)

	def post(self, request: Request, *args, **kwargs) -> Response:
		action = request.data.get("action")
		trade_id = request.data.get("trade_id")

		if not action or not trade_id:
			raise exceptions.ParseError("Action and trade_id are required.")

		if not Trade.objects.filter(id=trade_id).exists():
			raise exceptions.NotFound("Trade not found.")

		if action.upper() not in TradeStatuses._member_names_:
			raise exceptions.ValidationError("Invalid action.")

		team = Team.objects.get(owner=request.user)

		if action.upper() == TradeStatuses.COUNTEROFFER.value:
			offer = request.data.get("offer", None)

			if offer is None:
				raise exceptions.ParseError("Offer is required for counteroffer action.")

			Trade.objects.get(pk=trade_id).make_counteroffer(
				offer=offer,
			)

		else:
			Trade.objects.get(pk=trade_id).make_route(TradeStatuses[action.upper()], team)

		return Response({"detail": f"Trade {action.lower()} action completed."}, status=status.HTTP_200_OK)

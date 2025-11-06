from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from trade.models import Trade
from trade.serializers.trade import TradeSerializer


class TradeViewSet(ModelViewSet):
	"""
	A viewset for viewing and editing trade instances.
	"""
	serializer_class = TradeSerializer
	permission_classes = (IsAuthenticated,)

	def get_queryset(self) -> Trade:
		"""Restrict trades to those involving the authenticated user's team."""  # noqa: DOC201
		user = self.request.user
		queryset = Trade.objects.filter(teams__owner=user).distinct()

		if not user.is_staff and not user.is_superuser:
			queryset = self.queryset.filter(user=user)

		return queryset

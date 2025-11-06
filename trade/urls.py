from django.urls import path

from .views.trade import TradeViewSet

urlpatterns = [
	# Pick endpoints
	path("trades/", TradeViewSet.as_view({"get": "list"}), name="trade-list"),
]

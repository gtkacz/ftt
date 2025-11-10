from django.conf.urls import include
from django.urls import path
from rest_framework import routers

from .views.trade import TradeViewSet
from .views.trade_action import TradeActionView

router = routers.DefaultRouter()

router.register(r"", TradeViewSet, basename="trade")

urlpatterns = [
	path("trades/actions/", TradeActionView.as_view(), name="trade-actions"),
	path("trades/", include(router.urls)),
]

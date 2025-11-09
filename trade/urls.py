from django.conf.urls import include
from django.urls import path
from rest_framework import routers

from .views.trade import TradeViewSet

router = routers.DefaultRouter()

router.register(r"trades", TradeViewSet, basename="trade")

urlpatterns = [
	path("", include(router.urls)),
]

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
	# Auth endpoints
	path("auth/register/", views.UserRegistrationView.as_view(), name="user-register"),
	path("auth/login/", views.login_view, name="user-login"),
	path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
	# User endpoints
	path("users/", views.UserListCreateView.as_view(), name="user-list-create"),
	path("users/<int:pk>/", views.UserDetailView.as_view(), name="user-detail"),
	# Team endpoints
	path("teams/", views.TeamListCreateView.as_view(), name="team-list-create"),
	path("teams/<int:pk>/", views.TeamDetailView.as_view(), name="team-detail"),
	path("teams/<int:pk>/salary/", views.team_salary_view, name="team-salary"),
	path("teams/<int:pk>/players/", views.team_players_view, name="team-players"),
	path("teams/<int:pk>/picks/", views.team_picks_view, name="team-picks"),
	# Player endpoints
	path("players/", views.PlayerListCreateView.as_view(), name="player-list-create"),
	path("players/<int:pk>/", views.PlayerDetailView.as_view(), name="player-detail"),
	# Notification endpoints
	path(
		"notifications/",
		views.NotificationView.as_view(),
		name="notification-list",
	),
	path(
		"notifications/<int:pk>/",
		views.NotificationView.as_view(),
		name="notification-actions",
	),
	# Trade endpoints
	path("trades/", views.TradeListCreateView.as_view(), name="trade-list-create"),
	path("trades/<int:pk>/", views.TradeDetailView.as_view(), name="trade-detail"),
	path("trades/<int:pk>/propose/", views.propose_trade_view, name="trade-propose"),
	path("trades/<int:pk>/execute/", views.execute_trade_view, name="trade-execute"),
	path("trades/<int:pk>/cancel/", views.cancel_trade_view, name="trade-cancel"),
	path("trades/<int:pk>/approve/", views.approve_trade_view, name="trade-approve"),
	path("trades/<int:pk>/veto/", views.veto_trade_view, name="trade-veto"),
	path("trades/validate/", views.validate_trade_view, name="trade-validate"),
	path("trades/<int:trade_pk>/assets/", views.TradeAssetListCreateView.as_view(), name="trade-assets"),
	# Trade Asset endpoints
	path("trade-assets/<int:pk>/", views.TradeAssetDetailView.as_view(), name="trade-asset-detail"),
	# Trade Offer endpoints
	path("trade-offers/", views.TradeOfferListView.as_view(), name="trade-offer-list"),
	path("trade-offers/<int:pk>/", views.TradeOfferDetailView.as_view(), name="trade-offer-detail"),
	path("trade-offers/<int:pk>/accept/", views.accept_offer_view, name="trade-offer-accept"),
	path("trade-offers/<int:pk>/reject/", views.reject_offer_view, name="trade-offer-reject"),
	path("trade-offers/<int:pk>/counter/", views.counter_offer_view, name="trade-offer-counter"),
]

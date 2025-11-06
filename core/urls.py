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
]

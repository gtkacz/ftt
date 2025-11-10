from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from draft.models import Pick
from draft.serializers.pick import PickSerializer

from .models import Notification, Player, Team, User
from .serializers import (
	NotificationSerializer,
	PlayerSerializer,
	SimplePlayerSerializer,
	TeamSerializer,
	UserRegistrationSerializer,
	UserSerializer,
	UserUpdateSerializer,
)


class UserRegistrationView(generics.CreateAPIView):
	queryset = User.objects.all()
	serializer_class = UserRegistrationSerializer
	permission_classes = (permissions.AllowAny,)

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()
		refresh = RefreshToken.for_user(user)
		return Response(
			{
				"user": UserSerializer(user).data,
				"refresh": str(refresh),
				"access": str(refresh.access_token),
			},
			status=status.HTTP_201_CREATED,
		)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_view(request):
	username = request.data.get("username")
	password = request.data.get("password")

	if username and password:
		user = authenticate(username=username, password=password)
		if user:
			refresh = RefreshToken.for_user(user)
			user.last_login = timezone.now()
			user.save()
			return Response({
				"user": UserSerializer(user).data,
				"refresh": str(refresh),
				"access": str(refresh.access_token),
			})

	return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


class UserListCreateView(generics.ListCreateAPIView):
	queryset = User.objects.all()
	serializer_class = UserSerializer
	filterset_fields = "__all__"


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = User.objects.all()
	serializer_class = UserSerializer
	filterset_fields = "__all__"

	def update(self, request, *args, **kwargs):
		instance = self.get_object()

		serializer = UserUpdateSerializer(instance, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)

		self.perform_update(serializer)

		return Response(serializer.data, status=status.HTTP_200_OK)


class TeamListCreateView(generics.ListCreateAPIView):
	queryset = Team.objects.all()
	serializer_class = TeamSerializer
	filterset_fields = (field.name for field in Team._meta.fields if field.name != "avatar")


class TeamDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Team.objects.all()
	serializer_class = TeamSerializer
	filterset_fields = (field.name for field in Team._meta.fields if field.name != "avatar")


@api_view(["GET"])
def team_salary_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		return Response({"total_salary": team.total_salary()})
	except Team.DoesNotExist:
		return Response({"error": "Team not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def team_players_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		players = team.players.all()
		serializer = PlayerSerializer(players, many=True)
		return Response({"total_players": team.total_players(), "players": serializer.data})
	except Team.DoesNotExist:
		return Response({"error": "Team not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def team_picks_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		picks = Pick.objects.filter(current_team=team)
		serializer = PickSerializer(picks, many=True)
		return Response({"picks": serializer.data})
	except Team.DoesNotExist:
		return Response({"error": "Team not found"}, status=status.HTTP_404_NOT_FOUND)


class PlayerListCreateView(generics.ListCreateAPIView):
	queryset = Player.objects.all()
	serializer_class = SimplePlayerSerializer
	filterset_fields = (field.name for field in Player._meta.fields if field.name != "metadata")


class PlayerDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Player.objects.all()
	serializer_class = PlayerSerializer
	filterset_fields = (field.name for field in Player._meta.fields if field.name != "metadata")
	ordering_fields = ("id", "name", "position", "team", "salary", "relevancy")


class NotificationView(generics.ListAPIView, generics.RetrieveUpdateDestroyAPIView):
	queryset = Notification.objects.all()
	serializer_class = NotificationSerializer
	filterset_fields = ("user", "is_read", "created_at", "level", "priority")
	ordering_fields = ("created_at",)

	def get_queryset(self):
		return self.queryset.filter(user=self.request.user).order_by("-created_at")

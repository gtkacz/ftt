from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from draft.models import Pick
from draft.serializers.pick import PickSerializer

from .models import Notification, Player, Team, Trade, TradeAsset, TradeOffer, User
from .serializers import (
	NotificationSerializer,
	PlayerSerializer,
	SimplePlayerSerializer,
	TeamSerializer,
	TradeAssetSerializer,
	TradeOfferSerializer,
	TradeSerializer,
	UserRegistrationSerializer,
	UserSerializer,
	UserUpdateSerializer,
)


class UserRegistrationView(generics.CreateAPIView):
	queryset = User.objects.all()
	serializer_class = UserRegistrationSerializer
	permission_classes = [permissions.AllowAny]

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
	filterset_fields = [field.name for field in Team._meta.fields if field.name != "avatar"]


class TeamDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Team.objects.all()
	serializer_class = TeamSerializer
	filterset_fields = [field.name for field in Team._meta.fields if field.name != "avatar"]


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
	filterset_fields = [field.name for field in Player._meta.fields if field.name != "metadata"]


class PlayerDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Player.objects.all()
	serializer_class = PlayerSerializer
	filterset_fields = [field.name for field in Player._meta.fields if field.name != "metadata"]
	ordering_fields = ["id", "name", "position", "team", "salary", "relevancy"]


class NotificationView(generics.ListAPIView, generics.RetrieveUpdateDestroyAPIView):
	queryset = Notification.objects.all()
	serializer_class = NotificationSerializer
	filterset_fields = ["user", "is_read", "created_at", "level", "priority"]
	ordering_fields = ["created_at"]

	def get_queryset(self):
		return self.queryset.filter(user=self.request.user).order_by("-created_at")


# Trade Views
class TradeListCreateView(generics.ListCreateAPIView):
	queryset = Trade.objects.all().prefetch_related("teams", "assets", "offers")
	serializer_class = TradeSerializer
	filterset_fields = ["status", "proposing_team"]

	def get_queryset(self):
		queryset = super().get_queryset()
		team_id = self.request.query_params.get("team")
		if team_id:
			queryset = queryset.filter(teams__id=team_id)
		return queryset


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Trade.objects.all().prefetch_related("teams", "assets", "offers")
	serializer_class = TradeSerializer


@api_view(["POST"])
def propose_trade_view(request, pk):
	try:
		trade = Trade.objects.get(pk=pk)
		trade.propose()
		serializer = TradeSerializer(trade)
		return Response(serializer.data)
	except Trade.DoesNotExist:
		return Response({"error": "Trade not found"}, status=status.HTTP_404_NOT_FOUND)
	except Exception as e:
		return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def execute_trade_view(request, pk):
	try:
		trade = Trade.objects.get(pk=pk)
		trade.execute()
		serializer = TradeSerializer(trade)
		return Response(serializer.data)
	except Trade.DoesNotExist:
		return Response({"error": "Trade not found"}, status=status.HTTP_404_NOT_FOUND)
	except Exception as e:
		return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def cancel_trade_view(request, pk):
	try:
		trade = Trade.objects.get(pk=pk)
		trade.status = "cancelled"
		trade.save()
		serializer = TradeSerializer(trade)
		return Response(serializer.data)
	except Trade.DoesNotExist:
		return Response({"error": "Trade not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def approve_trade_view(request, pk):
	try:
		trade = Trade.objects.get(pk=pk)
		trade.status = "approved"
		trade.approved_at = timezone.now()
		trade.approved_by = request.user
		trade.notes = request.data.get("notes", trade.notes)
		trade.save()
		serializer = TradeSerializer(trade)
		return Response(serializer.data)
	except Trade.DoesNotExist:
		return Response({"error": "Trade not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def veto_trade_view(request, pk):
	try:
		trade = Trade.objects.get(pk=pk)
		trade.status = "vetoed"
		trade.notes = request.data.get("reason", trade.notes)
		trade.save()
		serializer = TradeSerializer(trade)
		return Response(serializer.data)
	except Trade.DoesNotExist:
		return Response({"error": "Trade not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def validate_trade_view(request):
	from ftt.settings import LEAGUE_SETTINGS

	teams_ids = request.data.get("teams", [])
	assets_data = request.data.get("assets", [])

	teams = Team.objects.filter(id__in=teams_ids)
	team_impacts = {}
	errors = []
	warnings = []

	for team in teams:
		incoming_salary = 0
		outgoing_salary = 0
		incoming_players = 0
		outgoing_players = 0

		for asset_data in assets_data:
			if asset_data["asset_type"] == "player" and asset_data.get("player"):
				try:
					player = Player.objects.get(id=asset_data["player"])
					if hasattr(player, "contract"):
						salary = player.contract.salary
						if asset_data["receiving_team"] == team.id:
							incoming_salary += salary
							incoming_players += 1
						elif asset_data["giving_team"] == team.id:
							outgoing_salary += salary
							outgoing_players += 1
				except Player.DoesNotExist:
					errors.append(f"Player {asset_data['player']} not found")

		net_salary = incoming_salary - outgoing_salary
		net_players = incoming_players - outgoing_players
		new_salary = team.total_salary() + net_salary
		new_player_count = team.total_players() + net_players

		under_salary_cap = new_salary <= LEAGUE_SETTINGS.SALARY_CAP
		under_player_cap = new_player_count <= LEAGUE_SETTINGS.MAX_PLAYER_CAP

		if not under_salary_cap:
			errors.append(
				f"{team.name} would exceed salary cap. Current: {team.total_salary()}, "
				f"New: {new_salary}, Cap: {LEAGUE_SETTINGS.SALARY_CAP}"
			)

		if not under_player_cap:
			errors.append(
				f"{team.name} would exceed player cap. Current: {team.total_players()}, "
				f"New: {new_player_count}, Cap: {LEAGUE_SETTINGS.MAX_PLAYER_CAP}"
			)

		team_impacts[team.id] = {
			"net_salary": net_salary,
			"net_players": net_players,
			"under_salary_cap": under_salary_cap,
			"under_player_cap": under_player_cap,
			"new_salary": new_salary,
			"new_player_count": new_player_count,
			"current_salary": team.total_salary(),
			"current_player_count": team.total_players(),
			"salary_cap": LEAGUE_SETTINGS.SALARY_CAP,
			"max_player_cap": LEAGUE_SETTINGS.MAX_PLAYER_CAP,
		}

	return Response(
		{
			"valid": len(errors) == 0,
			"errors": errors,
			"warnings": warnings,
			"team_impacts": team_impacts,
		}
	)


# Trade Asset Views
class TradeAssetListCreateView(generics.ListCreateAPIView):
	queryset = TradeAsset.objects.all()
	serializer_class = TradeAssetSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		trade_id = self.kwargs.get("trade_pk")
		if trade_id:
			queryset = queryset.filter(trade_id=trade_id)
		return queryset

	def perform_create(self, serializer):
		trade_id = self.kwargs.get("trade_pk")
		if trade_id:
			serializer.save(trade_id=trade_id)
		else:
			serializer.save()


class TradeAssetDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = TradeAsset.objects.all()
	serializer_class = TradeAssetSerializer


# Trade Offer Views
class TradeOfferListView(generics.ListAPIView):
	queryset = TradeOffer.objects.all().select_related("trade", "team")
	serializer_class = TradeOfferSerializer
	filterset_fields = ["team", "status", "trade"]


class TradeOfferDetailView(generics.RetrieveAPIView):
	queryset = TradeOffer.objects.all().select_related("trade", "team")
	serializer_class = TradeOfferSerializer


@api_view(["POST"])
def accept_offer_view(request, pk):
	try:
		offer = TradeOffer.objects.get(pk=pk)
		message = request.data.get("message", "")
		offer.accept(message)
		serializer = TradeOfferSerializer(offer)
		return Response(serializer.data)
	except TradeOffer.DoesNotExist:
		return Response({"error": "Trade offer not found"}, status=status.HTTP_404_NOT_FOUND)
	except Exception as e:
		return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def reject_offer_view(request, pk):
	try:
		offer = TradeOffer.objects.get(pk=pk)
		message = request.data.get("message", "")
		offer.reject(message)
		serializer = TradeOfferSerializer(offer)
		return Response(serializer.data)
	except TradeOffer.DoesNotExist:
		return Response({"error": "Trade offer not found"}, status=status.HTTP_404_NOT_FOUND)
	except Exception as e:
		return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def counter_offer_view(request, pk):
	try:
		offer = TradeOffer.objects.get(pk=pk)
		message = request.data.get("message", "")
		new_trade = offer.counter(message)
		serializer = TradeSerializer(new_trade)
		return Response(serializer.data)
	except TradeOffer.DoesNotExist:
		return Response({"error": "Trade offer not found"}, status=status.HTTP_404_NOT_FOUND)
	except Exception as e:
		return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
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
	TradeApprovalSerializer,
	TradeAssetSerializer,
	TradeHistorySerializer,
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
@permission_classes([permissions.IsAuthenticated])
def approve_trade_view(request, pk):
	"""Approve a trade.

	DEPRECATED: Use commissioner_vote_view instead.
	Kept for backward compatibility.

	Allows commissioners to approve trades using the new voting system.
	Admins (is_superuser) can instantly approve.
	Staff (is_staff) votes count toward majority.

	Args:
		request: HTTP request with optional 'notes' field.
		pk: Trade primary key.

	Returns:
		Response with trade data and vote result.

	Raises:
		HTTP_403_FORBIDDEN: If user is not a commissioner.
		HTTP_404_NOT_FOUND: If trade doesn't exist.
		HTTP_400_BAD_REQUEST: If validation fails.
	"""
	try:
		trade = Trade.objects.get(pk=pk)

		# Check permissions
		if not request.user.is_staff and not request.user.is_superuser:
			return Response(
				{"error": "Only commissioners can approve trades"},
				status=status.HTTP_403_FORBIDDEN,
			)

		notes = request.data.get("notes", "")

		# Use new voting system
		result = trade.record_commissioner_vote(
			commissioner=request.user,
			vote="approve",
			notes=notes,
		)

		serializer = TradeSerializer(trade)
		return Response({"trade": serializer.data, "vote_result": result})

	except Trade.DoesNotExist:
		return Response(
			{"error": "Trade not found"},
			status=status.HTTP_404_NOT_FOUND,
		)
	except ValidationError as e:
		return Response(
			{"error": str(e)},
			status=status.HTTP_400_BAD_REQUEST,
		)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def veto_trade_view(request, pk):
	"""Veto a trade.

	DEPRECATED: Use commissioner_vote_view instead.
	Kept for backward compatibility.

	Allows commissioners to veto trades using the new voting system.
	Admins (is_superuser) can instantly veto.
	Staff (is_staff) votes count toward majority.

	Args:
		request: HTTP request with optional 'reason' field.
		pk: Trade primary key.

	Returns:
		Response with trade data and vote result.

	Raises:
		HTTP_403_FORBIDDEN: If user is not a commissioner.
		HTTP_404_NOT_FOUND: If trade doesn't exist.
		HTTP_400_BAD_REQUEST: If validation fails.
	"""
	try:
		trade = Trade.objects.get(pk=pk)

		# Check permissions
		if not request.user.is_staff and not request.user.is_superuser:
			return Response(
				{"error": "Only commissioners can veto trades"},
				status=status.HTTP_403_FORBIDDEN,
			)

		reason = request.data.get("reason", "")

		# Use new voting system
		result = trade.record_commissioner_vote(
			commissioner=request.user,
			vote="veto",
			notes=reason,
		)

		serializer = TradeSerializer(trade)
		return Response({"trade": serializer.data, "vote_result": result})

	except Trade.DoesNotExist:
		return Response(
			{"error": "Trade not found"},
			status=status.HTTP_404_NOT_FOUND,
		)
	except ValidationError as e:
		return Response(
			{"error": str(e)},
			status=status.HTTP_400_BAD_REQUEST,
		)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def commissioner_vote_view(request, pk):
	"""Allow commissioners to vote on a trade.

	The primary endpoint for commissioner approval workflow.
	Replaces separate approve_trade_view and veto_trade_view.

	Admins (is_superuser) can instantly approve/veto with a single vote.
	Staff (is_staff) votes count toward majority rule decision.

	Args:
		request: HTTP request with required 'vote' field ("approve" or "veto")
			and optional 'notes' field.
		pk: Trade primary key.

	Returns:
		Response with trade data and vote result containing:
			- decision_made (bool): Whether a final decision was reached.
			- final_status (str): Trade status if decision made.
			- votes_needed (int): Remaining votes needed for decision.
			- approve_count (int): Current approval votes.
			- veto_count (int): Current veto votes.
			- total_commissioners (int): Total number of commissioners.

	Raises:
		HTTP_403_FORBIDDEN: If user is not a commissioner.
		HTTP_404_NOT_FOUND: If trade doesn't exist.
		HTTP_400_BAD_REQUEST: If validation fails or vote is invalid.

	Examples:
		>>> # Admin instant approval
		>>> POST /api/trades/1/vote/
		>>> {"vote": "approve", "notes": "Trade looks fair"}
		>>> # Returns: {"trade": {...}, "vote_result": {"decision_made": True, "final_status": "approved"}}

		>>> # Regular commissioner vote
		>>> POST /api/trades/1/vote/
		>>> {"vote": "approve", "notes": "I support this trade"}
		>>> # Returns: {"trade": {...}, "vote_result": {"decision_made": False, "votes_needed": 2}}
	"""
	try:
		trade = Trade.objects.get(pk=pk)

		# Check permissions
		if not request.user.is_staff and not request.user.is_superuser:
			return Response(
				{"error": "Only commissioners can vote on trades"},
				status=status.HTTP_403_FORBIDDEN,
			)

		vote = request.data.get("vote")  # "approve" or "veto"
		notes = request.data.get("notes", "")

		if vote not in ["approve", "veto"]:
			return Response(
				{"error": "vote must be 'approve' or 'veto'"},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# Record vote using new voting system
		result = trade.record_commissioner_vote(
			commissioner=request.user,
			vote=vote,
			notes=notes,
		)

		serializer = TradeSerializer(trade)

		return Response({
			"trade": serializer.data,
			"vote_result": result,
		})

	except Trade.DoesNotExist:
		return Response(
			{"error": "Trade not found"},
			status=status.HTTP_404_NOT_FOUND,
		)
	except ValidationError as e:
		return Response(
			{"error": str(e)},
			status=status.HTTP_400_BAD_REQUEST,
		)
	except Exception as e:
		return Response(
			{"error": str(e)},
			status=status.HTTP_400_BAD_REQUEST,
		)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def trade_history_view(request, pk):
	"""Get complete timeline/history for a trade.

	Returns all historical events and commissioner votes for a trade.
	Access is restricted to teams involved in the trade or commissioners.

	Args:
		request: HTTP request.
		pk: Trade primary key.

	Returns:
		Response with:
			- trade_id: Trade ID.
			- status: Current trade status.
			- history: List of trade history events (ordered chronologically).
			- approvals: List of commissioner votes (if user has permission).

	Raises:
		HTTP_403_FORBIDDEN: If user doesn't have permission to view this trade.
		HTTP_404_NOT_FOUND: If trade doesn't exist.

	Examples:
		>>> # Team owner viewing their trade
		>>> GET /api/trades/1/history/
		>>> # Returns: {"trade_id": 1, "status": "waiting_approval", "history": [...], "approvals": []}

		>>> # Commissioner viewing trade
		>>> GET /api/trades/1/history/
		>>> # Returns: {"trade_id": 1, "status": "waiting_approval", "history": [...], "approvals": [...]}
	"""
	try:
		trade = Trade.objects.get(pk=pk)

		# Permission check
		user = request.user
		is_involved = trade.teams.filter(owner=user).exists()
		is_commissioner = user.is_staff or user.is_superuser

		if not is_involved and not is_commissioner:
			return Response(
				{"error": "You don't have permission to view this trade history"},
				status=status.HTTP_403_FORBIDDEN,
			)

		# Get history (ordered chronologically by created_at)
		history = trade.history.all()
		history_serializer = TradeHistorySerializer(history, many=True)

		# Get approvals if commissioner or trade in approval status
		approvals = []
		if is_commissioner or trade.status in ["waiting_approval", "approved", "vetoed"]:
			approvals = trade.approvals.all()
			approvals_serializer = TradeApprovalSerializer(approvals, many=True)
			approvals = approvals_serializer.data

		return Response({
			"trade_id": trade.id,
			"status": trade.status,
			"history": history_serializer.data,
			"approvals": approvals,
		})

	except Trade.DoesNotExist:
		return Response(
			{"error": "Trade not found"},
			status=status.HTTP_404_NOT_FOUND,
		)


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

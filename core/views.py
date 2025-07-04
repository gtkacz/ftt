from django.contrib.auth import authenticate
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiExample, OpenApiParameter,
                                   OpenApiResponse, extend_schema,
                                   extend_schema_view)
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from draft.models import Pick
from draft.serializers import PickSerializer

from .models import Player, Team, User
from .serializers import (PlayerSerializer, TeamSerializer,
                          UserRegistrationSerializer, UserSerializer)


@extend_schema_view(
	post=extend_schema(
		summary='Register a new user',
		description='Create a new user account with username, email, and password',
		tags=['Authentication'],
		examples=[
			OpenApiExample(
				'Registration Example',
				value={
					'username': 'john_doe',
					'email': 'john@example.com',
					'first_name': 'John',
					'last_name': 'Doe',
					'password': 'secure_password123',
					'password_confirm': 'secure_password123',
				},
				request_only=True,
			),
		],
		responses={
			201: OpenApiResponse(
				response=UserSerializer,
				description='User successfully created with JWT tokens',
				examples=[
					OpenApiExample(
						'Success Response',
						value={
							'user': {
								'id': 1,
								'username': 'john_doe',
								'email': 'john@example.com',
							},
							'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
							'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
						},
					)
				],
			),
			400: OpenApiResponse(description='Validation errors'),
		},
	)
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
				'user': UserSerializer(user).data,
				'refresh': str(refresh),
				'access': str(refresh.access_token),
			},
			status=status.HTTP_201_CREATED,
		)


@extend_schema(
	summary='User login',
	description='Authenticate user and return JWT tokens',
	tags=['Authentication'],
	request={
		'application/json': {
			'type': 'object',
			'properties': {
				'username': {'type': 'string', 'description': 'Username'},
				'password': {'type': 'string', 'description': 'Password'},
			},
			'required': ['username', 'password'],
		}
	},
	examples=[
		OpenApiExample(
			'Login Example',
			value={'username': 'john_doe', 'password': 'secure_password123'},
			request_only=True,
		),
	],
	responses={
		200: OpenApiResponse(
			description='Login successful',
			examples=[
				OpenApiExample(
					'Success Response',
					value={
						'user': {
							'id': 1,
							'username': 'john_doe',
							'email': 'john@example.com',
						},
						'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
						'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
					},
				)
			],
		),
		401: OpenApiResponse(description='Invalid credentials'),
	},
)
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
	username = request.data.get('username')
	password = request.data.get('password')

	if username and password:
		user = authenticate(username=username, password=password)
		if user:
			refresh = RefreshToken.for_user(user)
			return Response(
				{
					'user': UserSerializer(user).data,
					'refresh': str(refresh),
					'access': str(refresh.access_token),
				}
			)

	return Response(
		{'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED
	)


@extend_schema_view(
	get=extend_schema(
		summary='List all users',
		description='Retrieve a paginated list of all users in the system',
		tags=['Users'],
	),
	post=extend_schema(
		summary='Create a new user',
		description='Create a new user (admin only)',
		tags=['Users'],
	),
)
class UserListCreateView(generics.ListCreateAPIView):
	queryset = User.objects.all()
	serializer_class = UserSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get user details',
		description='Retrieve detailed information about a specific user',
		tags=['Users'],
	),
	put=extend_schema(
		summary='Update user',
		description='Update user information (full update)',
		tags=['Users'],
	),
	patch=extend_schema(
		summary='Partially update user',
		description='Partially update user information',
		tags=['Users'],
	),
	delete=extend_schema(
		summary='Delete user',
		description='Delete a user account',
		tags=['Users'],
	),
)
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = User.objects.all()
	serializer_class = UserSerializer


@extend_schema_view(
	get=extend_schema(
		summary='List all teams',
		description='Retrieve a paginated list of all teams with their basic info and stats',
		tags=['Teams'],
	),
	post=extend_schema(
		summary='Create a new team',
		description='Create a new team for a user',
		tags=['Teams'],
	),
)
class TeamListCreateView(generics.ListCreateAPIView):
	queryset = Team.objects.all()
	serializer_class = TeamSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get team details',
		description='Retrieve detailed information about a specific team',
		tags=['Teams'],
	),
	put=extend_schema(
		summary='Update team',
		description='Update team information (full update)',
		tags=['Teams'],
	),
	patch=extend_schema(
		summary='Partially update team',
		description='Partially update team information',
		tags=['Teams'],
	),
	delete=extend_schema(
		summary='Delete team',
		description='Delete a team',
		tags=['Teams'],
	),
)
class TeamDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Team.objects.all()
	serializer_class = TeamSerializer


@extend_schema(
	summary='Get team total salary',
	description='Calculate and return the total salary of all players on a team',
	tags=['Teams'],
	parameters=[
		OpenApiParameter(
			name='pk',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Team ID',
		),
	],
	responses={
		200: OpenApiResponse(
			description='Total salary calculated',
			examples=[
				OpenApiExample(
					'Salary Response', value={'total_salary': '125000000.00'}
				)
			],
		),
		404: OpenApiResponse(description='Team not found'),
	},
)
@api_view(['GET'])
def team_salary_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		return Response({'total_salary': team.total_salary()})
	except Team.DoesNotExist:
		return Response({'error': 'Team not found'}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
	summary='Get team players',
	description='Retrieve all players on a team along with the total player count',
	tags=['Teams'],
	parameters=[
		OpenApiParameter(
			name='pk',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Team ID',
		),
	],
	responses={
		200: OpenApiResponse(
			description='Team players retrieved',
			examples=[
				OpenApiExample(
					'Players Response',
					value={
						'total_players': 15,
						'players': [
							{
								'id': 1,
								'name': 'LeBron James',
								'salary': '50000000.00',
								'primary_position': 'F',
							}
						],
					},
				)
			],
		),
		404: OpenApiResponse(description='Team not found'),
	},
)
@api_view(['GET'])
def team_players_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		players = team.players.all()
		serializer = PlayerSerializer(players, many=True)
		return Response(
			{'total_players': team.total_players(), 'players': serializer.data}
		)
	except Team.DoesNotExist:
		return Response({'error': 'Team not found'}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
	summary='Get team draft picks',
	description='Retrieve all draft picks currently owned by a team',
	tags=['Teams'],
	parameters=[
		OpenApiParameter(
			name='pk',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Team ID',
		),
	],
	responses={
		200: OpenApiResponse(
			description='Team draft picks retrieved',
			examples=[
				OpenApiExample(
					'Picks Response',
					value={
						'picks': [
							{
								'id': 1,
								'draft_year': 2025,
								'round_number': 1,
								'protections': 'Top 3 protected',
							}
						]
					},
				)
			],
		),
		404: OpenApiResponse(description='Team not found'),
	},
)
@api_view(['GET'])
def team_picks_view(request, pk):
	try:
		team = Team.objects.get(pk=pk)
		picks = Pick.objects.filter(current_team=team)
		serializer = PickSerializer(picks, many=True)
		return Response({'picks': serializer.data})
	except Team.DoesNotExist:
		return Response({'error': 'Team not found'}, status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
	get=extend_schema(
		summary='List all players',
		description='Retrieve a paginated list of all players in the league',
		tags=['Players'],
		parameters=[
			OpenApiParameter(
				name='team',
				type=OpenApiTypes.INT,
				location=OpenApiParameter.QUERY,
				description='Filter by team ID',
				required=False,
			),
			OpenApiParameter(
				name='position',
				type=OpenApiTypes.STR,
				location=OpenApiParameter.QUERY,
				description='Filter by position (G, F, C)',
				required=False,
			),
			OpenApiParameter(
				name='is_rfa',
				type=OpenApiTypes.BOOL,
				location=OpenApiParameter.QUERY,
				description='Filter by RFA status',
				required=False,
			),
		],
	),
	post=extend_schema(
		summary='Create a new player',
		description='Add a new player to the league',
		tags=['Players'],
	),
)
class PlayerListCreateView(generics.ListCreateAPIView):
	queryset = Player.objects.all()
	serializer_class = PlayerSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get player details',
		description='Retrieve detailed information about a specific player',
		tags=['Players'],
	),
	put=extend_schema(
		summary='Update player',
		description='Update player information (full update)',
		tags=['Players'],
	),
	patch=extend_schema(
		summary='Partially update player',
		description='Partially update player information',
		tags=['Players'],
	),
	delete=extend_schema(
		summary='Delete player',
		description='Remove a player from the league',
		tags=['Players'],
	),
)
class PlayerDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Player.objects.all()
	serializer_class = PlayerSerializer

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (OpenApiExample, OpenApiParameter,
                                   OpenApiResponse, extend_schema,
                                   extend_schema_view)
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Draft, DraftPosition, Pick
from .serializers import (DraftPositionSerializer, DraftSerializer,
                          PickSerializer)


@extend_schema_view(
	get=extend_schema(
		summary='List draft picks',
		description='Retrieve a paginated list of all draft picks (draft capital)',
		tags=['Draft Capital'],
		parameters=[
			OpenApiParameter(
				name='draft_year',
				type=OpenApiTypes.INT,
				location=OpenApiParameter.QUERY,
				description='Filter by draft year',
				required=False,
			),
			OpenApiParameter(
				name='current_team',
				type=OpenApiTypes.INT,
				location=OpenApiParameter.QUERY,
				description='Filter by current team owner',
				required=False,
			),
		],
	),
	post=extend_schema(
		summary='Create a draft pick',
		description='Create a new draft pick asset',
		tags=['Draft Capital'],
	),
)
class PickListCreateView(generics.ListCreateAPIView):
	queryset = Pick.objects.all()
	serializer_class = PickSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get draft pick details',
		description='Retrieve detailed information about a specific draft pick',
		tags=['Draft Capital'],
	),
	put=extend_schema(
		summary='Update draft pick',
		description='Update draft pick information (used for trades)',
		tags=['Draft Capital'],
	),
	patch=extend_schema(
		summary='Partially update draft pick',
		description='Partially update draft pick information',
		tags=['Draft Capital'],
	),
	delete=extend_schema(
		summary='Delete draft pick',
		description='Remove a draft pick',
		tags=['Draft Capital'],
	),
)
class PickDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Pick.objects.all()
	serializer_class = PickSerializer


@extend_schema_view(
	get=extend_schema(
		summary='List drafts',
		description='Retrieve a paginated list of all draft events',
		tags=['Drafts'],
	),
	post=extend_schema(
		summary='Create a draft',
		description='Create a new draft event for a specific year',
		tags=['Drafts'],
	),
)
class DraftListCreateView(generics.ListCreateAPIView):
	queryset = Draft.objects.all()
	serializer_class = DraftSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get draft details',
		description='Retrieve detailed information about a specific draft including players and positions',
		tags=['Drafts'],
	),
	put=extend_schema(
		summary='Update draft',
		description='Update draft information',
		tags=['Drafts'],
	),
	patch=extend_schema(
		summary='Partially update draft',
		description='Partially update draft information',
		tags=['Drafts'],
	),
	delete=extend_schema(
		summary='Delete draft',
		description='Delete a draft event',
		tags=['Drafts'],
	),
)
class DraftDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Draft.objects.all()
	serializer_class = DraftSerializer


@extend_schema_view(
	get=extend_schema(
		summary='List draft positions',
		description='Retrieve a paginated list of all draft positions',
		tags=['Draft Positions'],
		parameters=[
			OpenApiParameter(
				name='draft',
				type=OpenApiTypes.INT,
				location=OpenApiParameter.QUERY,
				description='Filter by draft ID',
				required=False,
			),
			OpenApiParameter(
				name='is_pick_made',
				type=OpenApiTypes.BOOL,
				location=OpenApiParameter.QUERY,
				description='Filter by whether pick has been made',
				required=False,
			),
		],
	),
	post=extend_schema(
		summary='Create a draft position',
		description='Create a new draft position (usually done via generate-order endpoint)',
		tags=['Draft Positions'],
	),
)
class DraftPositionListCreateView(generics.ListCreateAPIView):
	queryset = DraftPosition.objects.all()
	serializer_class = DraftPositionSerializer


@extend_schema_view(
	get=extend_schema(
		summary='Get draft position details',
		description='Retrieve detailed information about a specific draft position',
		tags=['Draft Positions'],
	),
	put=extend_schema(
		summary='Update draft position',
		description='Update draft position information',
		tags=['Draft Positions'],
	),
	patch=extend_schema(
		summary='Partially update draft position',
		description='Partially update draft position information',
		tags=['Draft Positions'],
	),
	delete=extend_schema(
		summary='Delete draft position',
		description='Remove a draft position',
		tags=['Draft Positions'],
	),
)
class DraftPositionDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = DraftPosition.objects.all()
	serializer_class = DraftPositionSerializer


@extend_schema(
	summary='Generate draft order',
	description='Generate the complete draft order for a draft event, supporting both standard and snake draft formats',
	tags=['Drafts'],
	parameters=[
		OpenApiParameter(
			name='draft_id',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Draft ID to generate order for',
		),
	],
	request={
		'application/json': {
			'type': 'object',
			'properties': {
				'teams_order': {
					'type': 'array',
					'items': {'type': 'integer'},
					'description': 'Array of team IDs in draft order (worst to best record typically)',
				},
				'rounds': {
					'type': 'integer',
					'description': 'Number of rounds in the draft',
					'default': 1,
				},
			},
			'required': ['teams_order'],
		}
	},
	examples=[
		OpenApiExample(
			'Generate Order Example',
			value={'teams_order': [3, 1, 5, 2, 4], 'rounds': 2},
			request_only=True,
		),
	],
	responses={
		200: OpenApiResponse(
			description='Draft order generated successfully',
			examples=[
				OpenApiExample(
					'Success Response',
					value={'message': 'Draft order generated for 2 rounds'},
				)
			],
		),
		400: OpenApiResponse(description='Invalid request data'),
		404: OpenApiResponse(description='Draft not found'),
	},
)
@api_view(['POST'])
def generate_draft_order(request, draft_id):
	"""Generate draft order for a draft based on team standings or custom order"""
	try:
		draft = Draft.objects.get(id=draft_id)
		teams_order = request.data.get(
			'teams_order', []
		)  # List of team IDs in draft order
		rounds = request.data.get('rounds', 1)

		if not teams_order:
			return Response(
				{'error': 'teams_order is required'}, status=status.HTTP_400_BAD_REQUEST
			)

		# Clear existing draft positions
		DraftPosition.objects.filter(draft=draft).delete()

		overall_pick = 1
		for round_num in range(1, rounds + 1):
			pick_order = (
				teams_order
				if round_num % 2 == 1 or not draft.is_snake_draft
				else teams_order[::-1]
			)

			for pick_num, team_id in enumerate(pick_order, 1):
				DraftPosition.objects.create(
					draft=draft,
					team_id=team_id,
					round_number=round_num,
					pick_number=pick_num,
					overall_pick=overall_pick,
				)
				overall_pick += 1

		return Response({'message': f'Draft order generated for {rounds} rounds'})

	except Draft.DoesNotExist:
		return Response({'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
	summary='Make a draft pick',
	description='Select a player for a specific draft position during live draft',
	tags=['Draft Positions'],
	parameters=[
		OpenApiParameter(
			name='position_id',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Draft position ID to make pick for',
		),
	],
	request={
		'application/json': {
			'type': 'object',
			'properties': {
				'player_id': {
					'type': 'integer',
					'description': 'ID of the player to draft',
				}
			},
			'required': ['player_id'],
		}
	},
	examples=[
		OpenApiExample(
			'Make Pick Example',
			value={'player_id': 15},
			request_only=True,
		),
	],
	responses={
		200: OpenApiResponse(
			description='Pick made successfully',
			response=DraftPositionSerializer,
		),
		400: OpenApiResponse(
			description='Invalid request (pick already made, player unavailable, etc.)'
		),
		404: OpenApiResponse(description='Draft position or player not found'),
	},
)
@api_view(['POST'])
def make_draft_pick(request, position_id):
	"""Make a draft pick for a specific draft position"""
	try:
		position = DraftPosition.objects.get(id=position_id)
		player_id = request.data.get('player_id')

		if position.is_pick_made:
			return Response(
				{'error': 'Pick already made'}, status=status.HTTP_400_BAD_REQUEST
			)

		if not player_id:
			return Response(
				{'error': 'player_id is required'}, status=status.HTTP_400_BAD_REQUEST
			)

		from core.models import Player

		try:
			player = Player.objects.get(id=player_id)
		except Player.DoesNotExist:
			return Response(
				{'error': 'Player not found'}, status=status.HTTP_404_NOT_FOUND
			)

		# Check if player is in draftable players
		if not position.draft.draftable_players.filter(id=player_id).exists():
			return Response(
				{'error': 'Player not available in this draft'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# Make the pick
		position.selected_player = player
		position.is_pick_made = True
		from django.utils import timezone

		position.pick_made_at = timezone.now()
		position.save()

		# Assign player to team
		player.team = position.team
		player.save()

		return Response(DraftPositionSerializer(position).data)

	except DraftPosition.DoesNotExist:
		return Response(
			{'error': 'Draft position not found'}, status=status.HTTP_404_NOT_FOUND
		)


@extend_schema(
	summary='Get draft board',
	description='Retrieve the current state of the draft board with all positions and next pick',
	tags=['Drafts'],
	parameters=[
		OpenApiParameter(
			name='draft_id',
			type=OpenApiTypes.INT,
			location=OpenApiParameter.PATH,
			description='Draft ID to get board for',
		),
	],
	responses={
		200: OpenApiResponse(
			description='Draft board retrieved successfully',
			examples=[
				OpenApiExample(
					'Draft Board Response',
					value={
						'draft': {
							'id': 1,
							'year': 2025,
							'is_completed': False,
							'is_snake_draft': True,
						},
						'positions': [
							{
								'id': 1,
								'team_name': 'Lakers',
								'round_number': 1,
								'pick_number': 1,
								'overall_pick': 1,
								'selected_player_name': 'Victor Wembanyama',
								'is_pick_made': True,
							}
						],
						'next_pick': {
							'id': 2,
							'team_name': 'Pistons',
							'round_number': 1,
							'pick_number': 2,
							'overall_pick': 2,
							'is_pick_made': False,
						},
					},
				)
			],
		),
		404: OpenApiResponse(description='Draft not found'),
	},
)
@api_view(['GET'])
def draft_board(request, draft_id):
	"""Get the current state of the draft board"""
	try:
		draft = Draft.objects.get(id=draft_id)
		positions = DraftPosition.objects.filter(draft=draft).order_by('overall_pick')

		return Response(
			{
				'draft': DraftSerializer(draft).data,
				'positions': DraftPositionSerializer(positions, many=True).data,
				'next_pick': DraftPositionSerializer(
					positions.filter(is_pick_made=False).first()
				).data
				if positions.filter(is_pick_made=False).exists()
				else None,
			}
		)

	except Draft.DoesNotExist:
		return Response({'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)

from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Draft, DraftPick, Pick
from .serializers import (DraftPositionSerializer, DraftSerializer,
                          PickSerializer)


class PickListCreateView(generics.ListCreateAPIView):
	queryset = Pick.objects.all()
	serializer_class = PickSerializer
	filterset_fields = '__all__'


class PickDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Pick.objects.all()
	serializer_class = PickSerializer
	filterset_fields = '__all__'


class DraftListCreateView(generics.ListCreateAPIView):
	queryset = Draft.objects.all()
	serializer_class = DraftSerializer
	filterset_fields = '__all__'


class DraftDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = Draft.objects.all()
	serializer_class = DraftSerializer
	filterset_fields = '__all__'


class DraftPositionListCreateView(generics.ListCreateAPIView):
	queryset = DraftPick.objects.all()
	serializer_class = DraftPositionSerializer
	filterset_fields = '__all__'


class DraftPositionDetailView(generics.RetrieveUpdateDestroyAPIView):
	queryset = DraftPick.objects.all()
	serializer_class = DraftPositionSerializer
	filterset_fields = '__all__'


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
		DraftPick.objects.filter(draft=draft).delete()

		overall_pick = 1
		for round_num in range(1, rounds + 1):
			pick_order = teams_order if round_num % 2 == 1 else teams_order[::-1]

			for pick_num, team_id in enumerate(pick_order, 1):
				DraftPick.objects.create(
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


@api_view(['POST'])
def make_draft_pick(request, position_id):
	"""Make a draft pick for a specific draft position"""
	try:
		position = DraftPick.objects.get(id=position_id)
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

	except DraftPick.DoesNotExist:
		return Response(
			{'error': 'Draft position not found'}, status=status.HTTP_404_NOT_FOUND
		)


@api_view(['GET'])
def draft_board(request, draft_id):
	"""Get the current state of the draft board"""
	try:
		draft = Draft.objects.get(id=draft_id)
		positions = DraftPick.objects.filter(draft=draft).order_by('overall_pick')

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

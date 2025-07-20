import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from draft.models import Draft, DraftPick

logger = logging.getLogger(__name__)


class Command(BaseCommand):
	help = 'Automatically make picks for drafts where time has expired'

	def handle(self, *args, **options):
		self.stdout.write(f'Starting auto draft picker at {timezone.now()}')

		# Get all active drafts
		active_drafts = Draft.objects.filter(
			is_completed=False, starts_at__lte=timezone.now()
		)

		for draft in active_drafts:
			try:
				self.process_draft(draft)
			except Exception as e:
				logger.error(f'Error processing draft {draft.id}: {str(e)}')
				self.stdout.write(
					self.style.ERROR(f'Error processing draft {draft.id}: {str(e)}')
				)

		self.stdout.write(
			self.style.SUCCESS(f'Auto draft picker completed at {timezone.now()}')
		)

	def process_draft(self, draft):
		"""Process a single draft for auto picks"""
		# Find current pick for this draft
		current_pick = DraftPick.objects.filter(
			draft=draft, is_current=True, is_pick_made=False
		).first()

		if not current_pick:
			# No current pick means draft might be completed or waiting
			return

		# Check if time has expired
		time_left = current_pick.time_left_to_pick()

		if time_left <= 0:
			self.stdout.write(
				f'Making auto pick for draft {draft.id}, pick {current_pick.overall_pick}'
			)

			try:
				with transaction.atomic():
					# The make_pick method will handle auto selection if player is None
					selected_player = current_pick.make_pick(None)

					self.stdout.write(
						self.style.SUCCESS(
							f'Auto picked {selected_player} for {current_pick.pick.current_team.name}'
						)
					)

			except Exception as e:
				logger.error(f'Failed to make auto pick for draft {draft.id}: {str(e)}')
				raise
		else:
			self.stdout.write(
				f'Draft {draft.id} pick {current_pick.overall_pick} has {time_left} seconds remaining'
			)

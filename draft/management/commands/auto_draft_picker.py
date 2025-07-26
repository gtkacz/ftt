import logging
from collections.abc import Sequence
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from draft.models import Draft, DraftPick

logger = logging.getLogger(__name__)


class Command(BaseCommand):
	"""Automatically make picks for drafts where time has expired."""

	help = "Automatically make picks for drafts where time has expired"

	def add_arguments(self, parser) -> None:  # noqa: ANN001, D102, PLR6301
		parser.add_argument(
			"--verbose",
			action="store_true",
			help="Enable verbose logging",
			default=True,
		)

	def handle(self, *_: Sequence[Any], **options: dict[str, Any]) -> None:  # noqa: D102
		verbose: bool = options["verbose"] or False  # pyright: ignore[reportAssignmentType]

		if verbose:
			self.stdout.write(f"Starting auto draft picker at {timezone.now()}")

		# Get all active drafts
		active_drafts = Draft.objects.filter(is_completed=False, starts_at__lte=timezone.now())

		total_picks_made = 0
		active_drafts_count = active_drafts.count()

		if verbose and active_drafts_count == 0:
			self.stdout.write("No active drafts found")
			return

		for draft in active_drafts:
			try:
				picks_made = self.process_draft(draft, verbose=verbose)
				total_picks_made += picks_made
			except Exception as e:
				logger.exception(f"Error processing draft {draft.id}:")  # pyright: ignore[reportAttributeAccessIssue]
				self.stdout.write(self.style.ERROR(f"Error processing draft {draft.id}: {e!s}"))  # pyright: ignore[reportAttributeAccessIssue]

		if verbose:
			self.stdout.write(
				self.style.SUCCESS(
					f"Auto draft picker completed at {timezone.now()}. "
					f"Made {total_picks_made} picks across {active_drafts_count} drafts.",
				),
			)
		elif total_picks_made > 0:
			self.stdout.write(self.style.SUCCESS(f"Made {total_picks_made} auto picks"))

	def process_draft(self, draft: "Draft", *, verbose: bool = False) -> int:  # noqa: C901
		"""Process a single draft for auto picks."""  # noqa: DOC201
		picks_made = 0

		while True:
			# Find current pick for this draft
			current_pick = DraftPick.objects.filter(draft=draft, is_current=True, is_pick_made=False).first()

			if not current_pick:
				# No current pick means draft might be completed or waiting
				if verbose:
					self.stdout.write(f"No current pick found for draft {draft.id}, stopping processing")  # pyright: ignore[reportAttributeAccessIssue]
				break

			# Check if time has expired
			time_left = current_pick.time_left_to_pick()

			if time_left <= 0:
				if verbose:
					self.stdout.write(f"Making auto pick for draft {draft.id}, pick {current_pick.overall_pick}")  # pyright: ignore[reportAttributeAccessIssue]

				try:
					with transaction.atomic():
						# The make_pick method will handle auto selection if player is None
						selected_player = current_pick.make_pick(None, is_auto_pick=True)
						picks_made += 1

						logger.warning(
							f"Auto picked {selected_player} for {current_pick.pick.current_team.name} "  # pyright: ignore[reportAttributeAccessIssue]
							f"in draft {draft.id} (pick {current_pick.overall_pick})",  # pyright: ignore[reportAttributeAccessIssue]
						)

						if verbose:
							self.stdout.write(
								self.style.SUCCESS(
									f"Auto picked {selected_player} for {current_pick.pick.current_team.name}",  # pyright: ignore[reportAttributeAccessIssue]
								),
							)

				except Exception:
					logger.exception(f"Failed to make auto pick for draft {draft.id}:")  # pyright: ignore[reportAttributeAccessIssue]
					raise
			else:
				# This pick hasn't expired yet, stop processing this draft
				if verbose:
					self.stdout.write(
						f"Draft {draft.id} pick {current_pick.overall_pick} has {time_left:.1f} seconds remaining",  # pyright: ignore[reportAttributeAccessIssue]
					)
				break

		# Check if draft is now completed
		if not DraftPick.objects.filter(draft=draft, is_pick_made=False).exists():
			draft.is_completed = True
			draft.save()
			logger.info(f"Draft {draft.id} completed")  # pyright: ignore[reportAttributeAccessIssue]
			if verbose:
				self.stdout.write(self.style.SUCCESS(f"Draft {draft.id} completed"))  # pyright: ignore[reportAttributeAccessIssue]

		return picks_made

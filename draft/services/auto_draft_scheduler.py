import logging
import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from django.core.management import call_command
from django.utils import timezone

if TYPE_CHECKING:
	from draft.models.draft_pick import DraftPick

logger = logging.getLogger(__name__)


class AutoDraftScheduler:
	def __init__(self) -> None:
		"""Initialize the auto draft scheduler."""
		self.running = False
		self.timer = None
		self.lock = threading.Lock()

	def start(self):
		"""Start the smart auto draft scheduler."""
		with self.lock:
			if self.running:
				return

			self.running = True
			logger.debug("Smart auto draft scheduler started")

			self.timer = threading.Timer(
				1.0,
				self._process_and_schedule,
			)  # Delay initial database access to avoid AppConfig.ready() warning
			self.timer.daemon = True
			self.timer.start()

	def stop(self):
		"""Stop the auto draft scheduler."""
		with self.lock:
			self.running = False
			if self.timer:
				self.timer.cancel()
				self.timer = None
			logger.debug("Smart auto draft scheduler stopped")

	def _process_and_schedule(self) -> None:
		"""Process current picks and schedule next wake time."""
		if not self.running:
			return

		try:
			# Process any expired picks first
			call_command("auto_draft_picker")

			# Calculate next wake time
			next_wake_time = self._calculate_next_wake_time()

			if next_wake_time:
				delay_seconds = (next_wake_time - timezone.now()).total_seconds()
				delay_seconds = max(1, delay_seconds)  # Minimum 1 second delay

				logger.warning(f"Scheduling next auto-pick check in {delay_seconds:.1f} seconds at {next_wake_time}")

				# Schedule next execution
				self.timer = threading.Timer(delay_seconds, self._process_and_schedule)
				self.timer.daemon = True
				self.timer.start()
			else:
				# No active picks, check again in 1 hour
				logger.debug("No active draft picks found, checking again in 1 hour")
				self.timer = threading.Timer(3600, self._process_and_schedule)
				self.timer.daemon = True
				self.timer.start()

		except Exception:
			logger.exception("Error in smart auto draft scheduler:")
			# On error, retry in 1 minute
			if self.running:
				self.timer = threading.Timer(60, self._process_and_schedule)
				self.timer.daemon = True
				self.timer.start()

	def _calculate_next_wake_time(self) -> Optional[datetime]:
		"""Calculate when the next pick should expire across all active drafts."""  # noqa: DOC201
		try:
			from draft.models import Draft, DraftPick  # noqa: PLC0415

			# Get all active drafts
			active_drafts = Draft.objects.filter(is_completed=False, starts_at__lte=timezone.now())

			earliest_expiry = None

			for draft in active_drafts:
				# Find current pick for this draft
				current_pick = DraftPick.objects.filter(draft=draft, is_current=True, is_pick_made=False).first()

				if not current_pick or not current_pick.started_at:
					continue

				# Calculate when this pick will expire
				pick_expiry = self._calculate_pick_expiry_time(current_pick)

				if pick_expiry and (not earliest_expiry or pick_expiry < earliest_expiry):
					earliest_expiry = pick_expiry

		except Exception:
			logger.exception("Error calculating next wake time:")
			return None

		else:
			return earliest_expiry

	@staticmethod
	def _calculate_pick_expiry_time(draft_pick: "DraftPick") -> Optional[datetime]:
		"""Calculate the exact time when a draft pick will expire."""  # noqa: DOC201
		try:
			if not draft_pick.started_at:
				return None

			# Get draft settings
			time_limit_seconds = draft_pick.draft.time_limit_per_pick * 60
			lower_bound = draft_pick.draft.pick_hour_lower_bound
			upper_bound = draft_pick.draft.pick_hour_upper_bound

			# Start from when the pick began
			current_time = draft_pick.started_at
			remaining_seconds = time_limit_seconds

			while remaining_seconds > 0:
				# Find the next active period
				current_date = current_time.date()

				# Create today's active window
				window_start = timezone.make_aware(
					datetime.combine(current_date, datetime.min.time().replace(hour=lower_bound)),
				)
				window_end = timezone.make_aware(
					datetime.combine(current_date, datetime.min.time().replace(hour=upper_bound)),
				)

				# If we're before today's window, jump to window start
				if current_time < window_start:
					current_time = window_start

				# If we're after today's window, jump to tomorrow's window start
				elif current_time >= window_end:
					next_day = current_date + timedelta(days=1)
					current_time = timezone.make_aware(
						datetime.combine(next_day, datetime.min.time().replace(hour=lower_bound)),
					)
					continue

				# Calculate how much time we can consume in this window
				window_remaining = (window_end - current_time).total_seconds()
				time_to_consume = min(remaining_seconds, window_remaining)

				# Advance time and reduce remaining
				current_time += timedelta(seconds=time_to_consume)
				remaining_seconds -= time_to_consume

				# If we used up the whole window but still have time remaining,
				# move to the next day's window
				if remaining_seconds > 0 and time_to_consume == window_remaining:
					next_day = current_time.date() + timedelta(days=1)
					current_time = timezone.make_aware(
						datetime.combine(next_day, datetime.min.time().replace(hour=lower_bound)),
					)

		except Exception:
			logger.exception("Error calculating pick expiry time:")
			return None

		else:
			return current_time


# Global scheduler instance
scheduler = AutoDraftScheduler()


def start_auto_draft_scheduler():
	"""Start the global scheduler."""
	scheduler.start()


def stop_auto_draft_scheduler():
	"""Stop the global scheduler."""
	scheduler.stop()

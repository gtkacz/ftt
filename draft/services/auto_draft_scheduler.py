import logging
import threading
import time

from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)


class AutoDraftScheduler:
	def __init__(self, interval_minutes=1):
		self.interval_minutes = interval_minutes
		self.running = False
		self.thread = None

	def start(self):
		"""Start the auto draft scheduler"""
		if self.running:
			return

		self.running = True
		self.thread = threading.Thread(target=self._run, daemon=True)
		self.thread.start()
		logger.info('Auto draft scheduler started')

	def stop(self):
		"""Stop the auto draft scheduler"""
		self.running = False
		if self.thread:
			self.thread.join()
		logger.info('Auto draft scheduler stopped')

	def _run(self):
		"""Main scheduler loop"""
		while self.running:
			try:
				call_command('auto_draft_picker')
			except Exception as e:
				logger.error(f'Error in auto draft picker: {str(e)}')

			# Wait for the interval
			time.sleep(self.interval_minutes * 60)


# Global scheduler instance
scheduler = AutoDraftScheduler()


def start_auto_draft_scheduler():
	"""Start the global scheduler"""
	scheduler.start()


def stop_auto_draft_scheduler():
	"""Stop the global scheduler"""
	scheduler.stop()

from django.apps import AppConfig


class DraftConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'draft'

	def ready(self):
		"""Called when the app is ready"""
		# Only start scheduler in production or when running server
		import sys

		if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
			from .services.auto_draft_scheduler import start_auto_draft_scheduler

			start_auto_draft_scheduler()

from django.db import models


class Notification(models.Model):
	"""Model representing a notification for a user."""

	LEVEL_CHOICES = (
		("info", "Info"),
		("warning", "Warning"),
		("error", "Error"),
	)
	user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="notifications")
	message = models.CharField(max_length=255)
	is_read = models.BooleanField(default=False)
	priority = models.PositiveIntegerField(
		default=1,
		help_text="Priority of the notification, higher number means higher priority",
	)
	level = models.CharField(
		max_length=10,
		choices=LEVEL_CHOICES,
		default="info",
		help_text="Notification level",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"Notification for {self.user.username}: {self.message}"

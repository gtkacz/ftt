from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
	"""Custom user model for the application."""

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_approved = models.BooleanField(default=False, help_text="User is approved to participate in the league")

	def __str__(self) -> str:
		return self.username

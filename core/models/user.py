from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
	"""Custom user model for the application."""

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_approved = models.BooleanField(default=False, help_text="User is approved to participate in the league")
	phone_country_code = models.CharField(max_length=8, blank=True, help_text="User's cellphone country code")
	phone_number = models.CharField(max_length=31, blank=True, help_text="User's cellphone number")

	def __str__(self) -> str:
		return self.username

	@property
	def phone(self) -> str:
		"""Returns the full phone number including country code."""
		if self.phone_country_code and self.phone_number:
			return f"+{self.phone_country_code}{self.phone_number}"

		return ""

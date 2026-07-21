from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from unidecode import unidecode

User = get_user_model()

# Google mints ID tokens under either of these issuer values.
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleTokenError(Exception):
	"""Raised when a Google ID token cannot be verified or is otherwise unusable."""


class GoogleAuthService:
	@staticmethod
	def verify_credential(credential: str) -> dict:
		"""
		Verify a Google ID token (the GIS `credential`) and return its claims.

		Args:
			credential (str): The raw Google ID token supplied by the client.

		Returns:
			dict: The verified token payload (claims).

		Raises:
			GoogleTokenError: If sign-in is unconfigured, or the token is invalid,
				expired, has the wrong audience/issuer, or carries an unverified email.
		"""
		if not settings.GOOGLE_OAUTH_CLIENT_ID:
			raise GoogleTokenError("Google sign-in is not configured on the server")

		try:
			payload = id_token.verify_oauth2_token(
				credential,
				google_requests.Request(),
				settings.GOOGLE_OAUTH_CLIENT_ID,
			)
		except ValueError as exc:
			raise GoogleTokenError("Invalid Google credential") from exc

		if payload.get("iss") not in GOOGLE_ISSUERS:
			raise GoogleTokenError("Untrusted token issuer")

		if not payload.get("email_verified"):
			raise GoogleTokenError("Google account email is not verified")

		return payload

	@classmethod
	def resolve_user(cls, payload: dict) -> User:
		"""
		Return the app user for a verified Google token payload.

		Links by Google subject identifier first, then by verified email, otherwise
		creates a new unapproved user pending commissioner approval.

		Args:
			payload (dict): A verified Google ID token payload.

		Returns:
			User: The resolved (existing or newly created) user.
		"""
		sub = payload["sub"]
		email = payload["email"]

		with transaction.atomic():
			user = User.objects.filter(google_sub=sub).first()
			if user:
				return user

			user = User.objects.filter(email__iexact=email).first()
			if user:
				user.google_sub = sub
				user.save()
				return user

			user = User.objects.create_user(
				username=cls._unique_username(email),
				email=email,
				first_name=payload.get("given_name", ""),
				last_name=payload.get("family_name", ""),
				password=None,
			)
			user.google_sub = sub
			user.save()
			return user

	@staticmethod
	def _unique_username(email: str) -> str:
		"""Build a unique username from an email local-part, disambiguating collisions."""
		base = unidecode(email.split("@", 1)[0]).lower()
		base = "".join(ch for ch in base if ch.isalnum() or ch in {".", "_", "-"}) or "user"

		username = base
		suffix = 1
		while User.objects.filter(username=username).exists():
			suffix += 1
			username = f"{base}{suffix}"

		return username

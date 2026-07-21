from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APIClient

from core.services.google_auth_service import GoogleAuthService

User = get_user_model()

VALID_PAYLOAD = {
	"iss": "https://accounts.google.com",
	"sub": "1234567890",
	"email": "player@example.com",
	"email_verified": True,
	"given_name": "Jordan",
	"family_name": "Rivers",
}

VERIFY_TARGET = "core.services.google_auth_service.id_token.verify_oauth2_token"


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class GoogleLoginEndpointTests(TestCase):
	def setUp(self) -> None:
		self.client = APIClient()
		self.url = reverse("user-google-login")

	def _post(self, credential: str = "google-id-token") -> Response:
		return self.client.post(self.url, {"credential": credential}, format="json")

	@patch(VERIFY_TARGET)
	def test_new_user_created_pending_approval(self, mock_verify: MagicMock) -> None:
		mock_verify.return_value = dict(VALID_PAYLOAD)

		resp = self._post()

		self.assertEqual(resp.status_code, 200)
		self.assertIn("access", resp.data)
		self.assertIn("refresh", resp.data)

		user = User.objects.get(email="player@example.com")
		self.assertFalse(user.is_approved)
		self.assertTrue(user.is_active)
		self.assertEqual(user.google_sub, "1234567890")
		self.assertEqual(user.first_name, "Jordan")
		self.assertFalse(user.has_usable_password())

	@patch(VERIFY_TARGET)
	def test_links_existing_user_by_email(self, mock_verify: MagicMock) -> None:
		existing = User.objects.create_user(
			username="existing",
			email="player@example.com",
		)
		mock_verify.return_value = dict(VALID_PAYLOAD)

		resp = self._post()

		self.assertEqual(resp.status_code, 200)
		existing.refresh_from_db()
		self.assertEqual(existing.google_sub, "1234567890")
		self.assertEqual(User.objects.filter(email="player@example.com").count(), 1)

	@patch(VERIFY_TARGET)
	def test_returning_user_matched_by_sub(self, mock_verify: MagicMock) -> None:
		existing = User.objects.create_user(
			username="existing",
			email="old-address@example.com",
		)
		existing.google_sub = "1234567890"
		existing.save()
		mock_verify.return_value = dict(VALID_PAYLOAD)
		count_before = User.objects.count()

		resp = self._post()

		self.assertEqual(resp.status_code, 200)
		self.assertEqual(User.objects.count(), count_before)
		self.assertEqual(resp.data["user"]["id"], existing.id)

	@patch(VERIFY_TARGET)
	def test_unverified_email_is_rejected(self, mock_verify: MagicMock) -> None:
		mock_verify.return_value = dict(VALID_PAYLOAD, email_verified=False)
		count_before = User.objects.count()

		resp = self._post()

		self.assertEqual(resp.status_code, 401)
		self.assertEqual(User.objects.count(), count_before)

	@patch(VERIFY_TARGET)
	def test_untrusted_issuer_is_rejected(self, mock_verify: MagicMock) -> None:
		mock_verify.return_value = dict(VALID_PAYLOAD, iss="evil.example.com")
		count_before = User.objects.count()

		resp = self._post()

		self.assertEqual(resp.status_code, 401)
		self.assertEqual(User.objects.count(), count_before)

	@patch(VERIFY_TARGET)
	def test_invalid_token_is_rejected(self, mock_verify: MagicMock) -> None:
		mock_verify.side_effect = ValueError("Token has wrong audience")

		resp = self._post()

		self.assertEqual(resp.status_code, 401)

	def test_missing_credential_is_bad_request(self) -> None:
		resp = self.client.post(self.url, {}, format="json")

		self.assertEqual(resp.status_code, 400)

	@override_settings(GOOGLE_OAUTH_CLIENT_ID="")
	@patch(VERIFY_TARGET)
	def test_unconfigured_server_is_rejected(self, mock_verify: MagicMock) -> None:
		mock_verify.return_value = dict(VALID_PAYLOAD)

		resp = self._post()

		self.assertEqual(resp.status_code, 401)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class UniqueUsernameTests(TestCase):
	def test_username_collision_is_disambiguated(self) -> None:
		User.objects.create_user(username="player", email="a@example.com")

		user = GoogleAuthService.resolve_user({
			"sub": "sub-1",
			"email": "player@example.com",
			"given_name": "",
			"family_name": "",
		})

		self.assertNotEqual(user.username, "player")
		self.assertTrue(user.username.startswith("player"))

from collections.abc import Sequence
from typing import Any

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet


class HealthCheckViewSet(ViewSet):
	"""HealthCheckViewSet is a viewset that provides a health check endpoint for the API."""

	permission_classes = (AllowAny,)

	@staticmethod
	def list(*_: Sequence[Any], **__: dict[str, Any]) -> Response:
		"""
		Health check endpoint for the API.

		Returns:
			Response: A response indicating the server is up.
		"""
		return Response(data="Server is up.", status=status.HTTP_200_OK)

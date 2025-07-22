from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import AllowAny


class HealthCheckViewSet(ViewSet):
	permission_classes = [AllowAny]

	def list(self, *args, **kwargs) -> Response:
		"""
		Health check endpoint for the API.

		Returns:
			Response: A response indicating the server is up.
		"""
		return Response(data='Server is up.', status=status.HTTP_200_OK)
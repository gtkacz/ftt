from rest_framework import generics
from .models import Pick, Draft
from .serializers import PickSerializer, DraftSerializer

class PickListCreateView(generics.ListCreateAPIView):
    queryset = Pick.objects.all()
    serializer_class = PickSerializer

class PickDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Pick.objects.all()
    serializer_class = PickSerializer

class DraftListCreateView(generics.ListCreateAPIView):
    queryset = Draft.objects.all()
    serializer_class = DraftSerializer

class DraftDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Draft.objects.all()
    serializer_class = DraftSerializer
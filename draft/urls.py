from django.urls import path
from . import views

urlpatterns = [
    # Pick endpoints
    path('picks/', views.PickListCreateView.as_view(), name='pick-list-create'),
    path('picks/<int:pk>/', views.PickDetailView.as_view(), name='pick-detail'),
    
    # Draft endpoints
    path('drafts/', views.DraftListCreateView.as_view(), name='draft-list-create'),
    path('drafts/<int:pk>/', views.DraftDetailView.as_view(), name='draft-detail'),
]
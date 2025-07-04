from django.urls import path

from . import views

urlpatterns = [
	# Pick endpoints
	path('picks/', views.PickListCreateView.as_view(), name='pick-list-create'),
	path('picks/<int:pk>/', views.PickDetailView.as_view(), name='pick-detail'),
	# Draft endpoints
	path('drafts/', views.DraftListCreateView.as_view(), name='draft-list-create'),
	path('drafts/<int:pk>/', views.DraftDetailView.as_view(), name='draft-detail'),
	path(
		'drafts/<int:draft_id>/generate-order/',
		views.generate_draft_order,
		name='generate-draft-order',
	),
	path('drafts/<int:draft_id>/board/', views.draft_board, name='draft-board'),
	# Draft Position endpoints
	path(
		'draft-positions/',
		views.DraftPositionListCreateView.as_view(),
		name='draft-position-list-create',
	),
	path(
		'draft-positions/<int:pk>/',
		views.DraftPositionDetailView.as_view(),
		name='draft-position-detail',
	),
	path(
		'draft-positions/<int:position_id>/pick/',
		views.make_draft_pick,
		name='make-draft-pick',
	),
]

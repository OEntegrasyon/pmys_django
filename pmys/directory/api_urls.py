from django.urls import path
from .api_views import (
    NextIdsView, TreeView, OrganizationsView, OrganizationDetailView,
    GroupsView, GroupDetailView,
    UsersView, UserDetailView, UserMoveView, UserActiveView,
    ExportView, ImportValidateView, ImportApplyView, ImportUploadView
)

app_name = "ldap_api"

urlpatterns = [
    path("tree/", TreeView.as_view()),

    path("organizations/", OrganizationsView.as_view()),
    path("organizations/<str:b64dn>/", OrganizationDetailView.as_view()),

    path("groups/", GroupsView.as_view()),
    path("groups/<str:b64dn>/", GroupDetailView.as_view()),

    path("users/", UsersView.as_view()),
    path("users/<str:b64dn>/", UserDetailView.as_view()),
    path("users/<str:b64dn>/move", UserMoveView.as_view()),
    path("users/<str:b64dn>/active/", UserActiveView.as_view()),

    path("export/", ExportView.as_view()),

    path("import/upload/", ImportUploadView.as_view()),
    path("import/validate/", ImportValidateView.as_view()),
    path("import/apply/", ImportApplyView.as_view()),

    path("next-ids/", NextIdsView.as_view(), name="ldap-next-ids"),
]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LdapUserViewSet, LdapGroupViewSet, LdapOrganizationViewSet

app_name='ldap'

router = DefaultRouter()
router.register(r'users', LdapUserViewSet)
router.register(r'groups', LdapGroupViewSet)
router.register(r'organizations', LdapOrganizationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

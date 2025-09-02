from rest_framework import viewsets
from .models import LdapUser, LdapGroup, LdapOrganization
from .serializers import LdapUserSerializer, LdapGroupSerializer, LdapOrganizationSerializer

class LdapUserViewSet(viewsets.ModelViewSet):
    queryset = LdapUser.objects.all().order_by('username')
    serializer_class = LdapUserSerializer

class LdapGroupViewSet(viewsets.ModelViewSet):
    queryset = LdapGroup.objects.all().order_by('name')
    serializer_class = LdapGroupSerializer

class LdapOrganizationViewSet(viewsets.ModelViewSet):
    queryset = LdapOrganization.objects.all().order_by('name')
    serializer_class = LdapOrganizationSerializer

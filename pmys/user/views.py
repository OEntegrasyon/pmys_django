from rest_framework import viewsets
from .models import User, Group, Organization
from .serializers import UserSerializer, GroupSerializer, OrganizationSerializer
from  utils.pagination import OptionalPagination

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    pagination_class = OptionalPagination

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by('name')
    serializer_class = GroupSerializer
    pagination_class = OptionalPagination

class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all().order_by('name')
    serializer_class = OrganizationSerializer
    pagination_class = OptionalPagination

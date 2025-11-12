from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.views import APIView

from nexus.users.models import User


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "language", "is_active"]


class UserDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(self.request.user, many=False)
        return Response(serializer.data)

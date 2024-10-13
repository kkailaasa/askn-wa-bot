import logging
from rest_framework import generics, mixins
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from .serializers import UserRegistrationSerializer

from . import helpers

logger = logging.getLogger(__name__)


class CreateUserApi(mixins.CreateModelMixin, generics.GenericAPIView):
    serializer_class = UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                response_register = helpers.register_user(request)
                if type(response_register) == User:
                    response_register = "user created"
                logger.info("response from helper: " + str(response_register))
                return Response(response_register, status=status.HTTP_200_OK)
            return Response("Invalid Data", status=status.HTTP_400_BAD_REQUEST)
        except Exception as ex:
            logging.error('Error at CreateUserApi', 'post', exc_info=ex)
            return Response("Server Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework import generics, status, viewsets, mixins, authentication, exceptions
from rest_framework.response import Response

from rest_framework.permissions import IsAuthenticated  # Import the permission class
from . import helpers
from user_registrations import helpers as ur_helpers
from .models import UserProfile, EPassportNumber
from .serializers import UserProfileApiRequestSerializer, EpassportNumberSerializer
from staff_dashboard.serializers import UserProfileSerializer

logger = logging.getLogger(__name__)


class UserProfileApi(LoginRequiredMixin, generics.GenericAPIView):
    serializer_class = UserProfileApiRequestSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            user_profile = UserProfile.objects.filter(user=self.request.user).first()
            response_serializer = UserProfileSerializer(user_profile)
            return Response(response_serializer.data)
        except UserProfile.DoesNotExist:
            return Response("User not found", status=status.HTTP_404_NOT_FOUND)
        except Exception as ex:
            logging.error("Error at UserProfileApi", "get", exc_info=ex)
            return Response(
                "Server Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, *args, **kwargs):
        try:
            user_profile = self.get_create_user_profile()
            serializer = self.serializer_class(
                user_profile, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                updated_instance = serializer.instance
                response_serializer = UserProfileSerializer(updated_instance)
                return Response(response_serializer.data)
      
            return Response("Invalid Data", status=status.HTTP_400_BAD_REQUEST)
        except Exception as ex:
            logging.error("Error at CreateUserApi", "post", exc_info=ex)
            return Response(
                "Server Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

      
    def get_create_user_profile(self):
        try:
            user_profile = UserProfile.objects.get(user=self.request.user)
        except UserProfile.DoesNotExist:
            user_profile = UserProfile.objects.create(
                user=self.request.user,
            )
        return user_profile

class EPassportApi(mixins.CreateModelMixin, generics.GenericAPIView):
    serializer_class = EpassportNumberSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            if self.request.user is not None:
                user_profile = UserProfile.objects.filter(
                    user=self.request.user
                ).first()

                if (user_profile is not None and (user_profile.first_name is None or user_profile.phone_number is None)):
                    print("----------> populate_user_profile")
                    ur_helpers.populate_user_profile_by_email(user_profile.email)

                # Get or create e-Passport for existing profile
                serialized_passport = self.serializer_class(
                    self.get_create_epassport_by_user_profile(user_profile)
                )
                return Response(serialized_passport.data)

            return Response("Bad request", status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response("User not found", status=status.HTTP_204_NO_CONTENT)
        except Exception as ex:
            print(ex)
            logging.error("Error at UserProfileApi", "get", exc_info=ex)
            return Response(
                "Server Error", status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_create_epassport_by_user_profile(self, user_profile):
        if user_profile is None:
            user = self.request.user
            user_profile = UserProfile.objects.create(user = user, email = user.email)
        epassport: EPassportNumber = None
        try:
            epassport = EPassportNumber.objects.get(user_profile=user_profile)
        except EPassportNumber.DoesNotExist:
            epassport = helpers.create_epassport_number(user_profile=user_profile)
        return epassport

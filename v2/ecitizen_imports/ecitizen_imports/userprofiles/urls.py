from django.urls import path

from .views import UserProfileUpsertView
from .user_profile_api import UserProfileApi, EPassportApi


urlpatterns = [
    path("api/user_profile/", UserProfileApi.as_view(), name="user-profile-api"),
    path("api/epassport/", EPassportApi.as_view(), name="epassport-api"),
    path("", UserProfileUpsertView.as_view(), name="profile_me"),
]

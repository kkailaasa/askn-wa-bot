from django.urls import path
from .views import UserRegistrationView, verify_token
from .user_registration_api import CreateUserApi

urlpatterns = [
    path('', UserRegistrationView.as_view(), name='user-registration'),
    #path('test', register_user, name='test-email'),
    path('verify/<str:token>/', verify_token, name='verify'),
    path('api/register-user', CreateUserApi.as_view(), name='user-reg-api')
]

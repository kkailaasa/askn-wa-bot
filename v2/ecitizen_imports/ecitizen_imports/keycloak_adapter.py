from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect

class KeycloakAdapter(DefaultSocialAccountAdapter):
    def on_authentication_error(
        self,
        request,
        provider,
        error=None,
        exception=None,
        extra_context=None,
    ):
        if request.GET.get('error') == 'temporarily_unavailable':
            raise ImmediateHttpResponse(redirect('/'))
        else:
            return super().on_authentication_error(
                request,
                provider,
                error,
                exception,
                extra_context,
            )
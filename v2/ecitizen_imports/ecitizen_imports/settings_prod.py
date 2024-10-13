import os
from .settings_db import DATABASES
from .settings import BASE_DIR

# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG = False
DEBUG = eval(os.getenv('DJANGO_DEBUG') or 'False')

# DEBUG_API_REQUESTS = False

SESSION_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r'^healthcheck/$']

CSRF_COOKIE_SECURE = True

ALLOWED_HOSTS = ['ecitizen.kailasamailer.com',
                 'kailasa.ecitizen.info',
                 'devc-ecitizen.kailasamailer.com',
                 'ec-prod-lb.kailasamailer.com',
                 '95.217.168.140',
                 #'65.109.222.197'
                 ]

CSRF_TRUSTED_ORIGINS = [
    'https://ecitizen.kailasamailer.com',
    'https://kailasa.ecitizen.info',
    'https://ec-prod-lb.kailasamailer.com',
]

STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = []

EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
ANYMAIL = {
    'DEBUG_API_REQUESTS': True,
    "SENDGRID_API_KEY": "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",
    "CLICK_TRACKING": True,
    "IGNORE_UNSUPPORTED_FEATURES": True,
    'WEBHOOK_SECRET': '1234:1234',
}

import os

KEYCLOAK_SERVER_URL = 'https://login.ecitizen.info/auth/'
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM')
KEYCLOAK_API_CLIENT_ID = os.getenv('KEYCLOAK_API_CLIENT_ID')
KEYCLOAK_API_CLIENT_SECRET = os.getenv('KEYCLOAK_API_CLIENT_SECRET')
KEYCLOAK_USER_NAME=os.getenv('KEYCLOAK_USER_NAME')
KEYCLOAK_PASSWORD=os.getenv('KEYCLOAK_PASSWORD')

ACCOUNT_DEFAULT_HTTP_PROTOCOL='https'

SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
        "APPS": [
            {
                "provider_id": "keycloak",
                "name": "My Login Server",
                "client_id": "consent-django",
                "secret": "947d473a-023d-44bf-a4b7-49b20d450571",
                "settings": {
                    "server_url": "https://login.ecitizen.info/auth/realms/epassport/.well-known/openid-configuration",
                    # Optional token endpoint authentication method.
                    # May be one of "client_secret_basic", "client_secret_post"
                    # If omitted, a method from the the server's
                    # token auth methods list is used
                    #"token_auth_method": "client_secret_basic",
                },
            },
        ]
    }
    # local-django-consent
    # EFCUSsLVS9dDIhXYguUprrBMyLdFChC1
    # http://localhost:8000/accounts/keycloak/login/callback/
}


import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="https://18b44ca78ff447d0b2804aac568cdb7e@glitch.kailasamailer.com/2",
    integrations=[
        DjangoIntegration(),
    ],
    auto_session_tracking=False,

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1,

    # If you wish to associate users to errors (assuming you are using
    # django.contrib.auth) you may enable sending PII data.
    send_default_pii=True,
    environment="production"
)


CELERY_BROKER_URL = 'redis://redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis:6379/0'

from django.apps import AppConfig


class UserRegistrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_registrations'
    
    def ready(self):
        from . import email_webhook  # Import your signals module
        #email_webhook.register_signals()  # Call the register_signals() function

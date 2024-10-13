from django.contrib import admin
from .models import SentMessage, VerificationToken

@admin.register(VerificationToken)
class VerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'verified')
    search_fields = ('user__email', 'token', 'verified')
    #list_filter = ('user_type')

@admin.register(SentMessage)
class SentMessageAdmin(admin.ModelAdmin):
    list_display = ('esp', 'message_id', 'email', 'subject', 'body', 'status', 'timestamp')
    search_fields = ('esp', 'message_id', 'email', 'subject', 'body', 'status', 'timestamp')
    #list_filter = ('user_type')
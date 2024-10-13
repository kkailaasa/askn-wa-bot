import secrets
from django.contrib.auth.tokens import PasswordResetTokenGenerator

def generate_verification_token() -> str:
    # Generate a random URL-safe token with 32 characters
    return secrets.token_urlsafe(64)

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp) -> str:
        return str(user.pk) + str(timestamp) + str(user.email_verified)


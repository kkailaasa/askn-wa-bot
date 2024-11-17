# tasks/__init__.py

from .celery_tasks import (
    celery_app,
    process_message,
    check_phone,
    check_email,
    create_account,
    send_otp_email_task,
    verify_email_task
)

__all__ = [
    'celery_app',
    'process_message',
    'check_phone',
    'check_email',
    'create_account',
    'send_otp_email_task',
    'verify_email_task'
]
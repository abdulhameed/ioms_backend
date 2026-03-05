"""
Users app Celery tasks — Phase 2.
"""

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email(self, user_id, token, base_url="http://localhost:3000"):
    """Send email-verification / account-activation link to the new user."""
    from apps.users.models import CustomUser

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return

    verification_url = f"{base_url}/auth/verify-email?token={token}"
    try:
        send_mail(
            subject="Verify your IOMS account",
            message=(
                f"Hello {user.full_name or user.email},\n\n"
                f"Please verify your email address and set your password:\n"
                f"{verification_url}\n\n"
                f"This link expires in 72 hours.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_account_unlock_email(self, user_id):
    """Notify a user that their account was locked and will auto-unlock."""
    from apps.users.models import CustomUser

    try:
        user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return

    try:
        send_mail(
            subject="IOMS account temporarily locked",
            message=(
                f"Hello {user.full_name or user.email},\n\n"
                f"Your account has been temporarily locked due to 5 failed "
                f"login attempts.\n"
                f"It will automatically unlock after 30 minutes.\n\n"
                f"If this was not you, please contact your administrator.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)

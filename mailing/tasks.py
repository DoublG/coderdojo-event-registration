from celery import shared_task
from django.core.mail import send_mail

from accounts.models import User


@shared_task
def send_email_to_user(user_id, subject, message):
    try:
        user = User.objects.get(pk=user_id)

        if not user.email:
            return {"status": "skipped", "reason": "no email"}

        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return {"status": "sent", "user_id": user_id}

    except User.DoesNotExist:
        return {"status": "skipped", "reason": "user not found"}

    except Exception as exc:
        return {
            "status": "failed",
            "user_id": user_id,
            "error": str(exc),
        }


@shared_task
def send_mail_to_all_users(subject, message):
    user_ids = (
        User.objects
        .exclude(email="")
        .values_list("pk", flat=True)
    )

    for user_id in user_ids.iterator():
        send_email_to_user.delay(
            user_id,
            subject,
            message,
        )

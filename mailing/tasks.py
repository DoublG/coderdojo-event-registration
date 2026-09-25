from celery import shared_task
from django.core.mail import EmailMultiAlternatives

@shared_task
def process_bounces():
    # Connect to your IMAP mailbox
    # Find new bounce messages
    # Parse them
    # Update EmailMessage records
    pass

@shared_task
def send_pending_emails():
    # Find emails that need to be sent
    # Queue/send them
    pass

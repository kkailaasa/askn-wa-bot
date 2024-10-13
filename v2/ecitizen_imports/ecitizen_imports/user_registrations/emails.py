from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.core.mail import send_mail
from django.contrib.auth.models import User
    
from urllib.parse import urlparse

def send_verification_email(request, user: User, token: str):
    verification_link = reverse('verify', args=[token])
    print("--------send_verification_email=============")
    current_url = request.build_absolute_uri()
    parsed_url = urlparse(current_url)
    base_url = parsed_url.scheme + "://" + parsed_url.netloc
    verification_url = f"{base_url}{verification_link}"
    email_subject = "Verify your email"
    context = {
        'user': user,
        'verification_link': verification_url,
    }
    
    html_message = render_to_string('email_templates/verification_email.html', context)
    plain_message = strip_tags(html_message)  # Strip HTML tags for the plain text version
    
    # Send the email using Django's send_mail() function and the AnyMail backend
    send_mail(
        subject=email_subject,
        message=plain_message,
        from_email="KAILASA'S ECitizen Portal <ecitizen@kailasa.email>",
        recipient_list=[user.email],
        html_message=html_message,
    )
    
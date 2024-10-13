from anymail.signals import tracking, post_send
from django.dispatch import receiver
from .models import SentMessage

@receiver(tracking, weak=False)
def handle_click(sender, event, esp_name, **kwargs):
    print("Recipient %s %s url %s" % (event.recipient, event.event_type, event.click_url))
    SentMessage.objects.create(
            esp=esp_name,
            message_id=event.message_id,  # might be None if send failed
            email=event.recipient,
            subject="tracking data",
            body=str(event.__dict__),
            status=event.event_type,  # 'sent' or 'rejected' or ...
            timestamp=event.timestamp
        )

from datetime import timezone
import datetime
@receiver(post_send)
def log_sent_message(sender, message, status, esp_name, **kwargs):
    # This assumes you've implemented a SentMessage model for tracking sends.
    # status.recipients is a dict of email: status for each recipient
    print("Received items count: {}", status.recipients.items())
    # Getting the current date
    # and time
    dt = datetime.datetime.now(timezone.utc)
    
    utc_time = dt.replace(tzinfo=timezone.utc)
    for email, recipient_status in status.recipients.items():
        SentMessage.objects.create(
            esp=esp_name,
            message_id=recipient_status.message_id,  # might be None if send failed
            email=email,
            subject=message.subject,
            body=message.body,
            status=recipient_status.status,  # 'sent' or 'rejected' or ...
            timestamp=utc_time
        )
        
        
"""
Recipient example@test.com queued url None
{'event_type': 'queued', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': '_vkYTtXh6y8Ob3pjEbVoRQ==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'processed', 'category': ['cat facts'], 'sg_event_id': '_vkYTtXh6y8Ob3pjEbVoRQ==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com deferred url None
{'event_type': 'deferred', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': '8fq7aiIvbusuud9Ypiyegg==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'deferred', 'category': ['cat facts'], 'sg_event_id': '8fq7aiIvbusuud9Ypiyegg==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'response': '400 try again later', 'attempt': '5'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': '400 try again later', 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com delivered url None
{'event_type': 'delivered', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'e0TUOZgWQQNLWZk1xDWTvw==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'delivered', 'category': ['cat facts'], 'sg_event_id': 'e0TUOZgWQQNLWZk1xDWTvw==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'response': '250 OK'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': '250 OK', 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com opened url None
{'event_type': 'opened', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'ooIvZq-03YUQjM5CeuTSAw==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'open', 'category': ['cat facts'], 'sg_event_id': 'ooIvZq-03YUQjM5CeuTSAw==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'useragent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)', 'ip': '255.255.255.255'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)'}
Recipient example@test.com clicked url http://www.sendgrid.com/
{'event_type': 'clicked', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'p7bcMCMWsOptsimsxhUrzg==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'click', 'category': ['cat facts'], 'sg_event_id': 'p7bcMCMWsOptsimsxhUrzg==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'useragent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)', 'ip': '255.255.255.255', 'url': 'http://www.sendgrid.com/'}, 'click_url': 'http://www.sendgrid.com/', 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)'}
Recipient example@test.com bounced url None
{'event_type': 'bounced', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'kYRzHIJUylTDHKCZayRjkQ==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'bounce', 'category': ['cat facts'], 'sg_event_id': 'kYRzHIJUylTDHKCZayRjkQ==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'reason': '500 unknown recipient', 'status': '5.0.0'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': '500 unknown recipient', 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com rejected url None
{'event_type': 'rejected', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'MpS29WkQIkac0kNcH1H6xA==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'dropped', 'category': ['cat facts'], 'sg_event_id': 'MpS29WkQIkac0kNcH1H6xA==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'reason': 'Bounced Address', 'status': '5.0.0'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': 'other', 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com complained url None
{'event_type': 'complained', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': '5JkOqaoFpUSIOODsrCpljA==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'spamreport', 'category': ['cat facts'], 'sg_event_id': '5JkOqaoFpUSIOODsrCpljA==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com unsubscribed url None
{'event_type': 'unsubscribed', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': '0d0Uyd8NciDmeSzOq0b-9w==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'unsubscribe', 'category': ['cat facts'], 'sg_event_id': '0d0Uyd8NciDmeSzOq0b-9w==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0'}, 'click_url': None, 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': None}
Recipient example@test.com unsubscribed url http://www.sendgrid.com/
{'event_type': 'unsubscribed', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'nSrTR1pjunpjpNV9pYb-EA==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'group_unsubscribe', 'category': ['cat facts'], 'sg_event_id': 'nSrTR1pjunpjpNV9pYb-EA==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'useragent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)', 'ip': '255.255.255.255', 'url': 'http://www.sendgrid.com/', 'asm_group_id': 10}, 'click_url': 'http://www.sendgrid.com/', 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)'}
Recipient example@test.com subscribed url http://www.sendgrid.com/
{'event_type': 'subscribed', 'timestamp': datetime.datetime(2023, 6, 18, 18, 46, 13, tzinfo=datetime.timezone.utc), 'event_id': 'FdPs6kM_yikZowLxKE2K5w==', 'esp_event': {'email': 'example@test.com', 'timestamp': 1687113973, 'smtp-id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'event': 'group_resubscribe', 'category': ['cat facts'], 'sg_event_id': 'FdPs6kM_yikZowLxKE2K5w==', 'sg_message_id': '14c5d75ce93.dfd.64b469.filter0001.16648.5515E0B88.0', 'useragent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)', 'ip': '255.255.255.255', 'url': 'http://www.sendgrid.com/', 'asm_group_id': 10}, 'click_url': 'http://www.sendgrid.com/', 'description': None, 'message_id': '<14c5d75ce93.dfd.64b469@ismtpd-555>', 'metadata': {}, 'mta_response': None, 'recipient': 'example@test.com', 'reject_reason': None, 'tags': ['cat facts'], 'user_agent': 'Mozilla/4.0 (compatible; MSIE 6.1; Windows XP; .NET CLR 1.1.4322; .NET CLR 2.0.50727)'}
"""
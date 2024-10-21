# Version Control Log

This document tracks the version history for the project, including the version number, release date, summary of changes, and contributors.

## Version History

---

### [v0.1.0] - 2024-10-20
##### Summary of Changes:
- Completed Basic Framework of the Application.
- Ingteration with NGPT Backend
- Basic API setup with FastAPI.
- Added `/check_phone`, `/check_email`, `/create_account`, `/send_email_otp`, and `/verify_email` `message` endpoints.
- Integrated with SendGrid for email OTPs.
- Configured Twilio for WhatsApp Interactions.
- Using Redis for caching responses from Keycloak

##### Contributors:
- **KAILASA Kenya** 

---

## Further Functionalities to be Completed for Release:

- Insert User Info into E-Citizen DB.
- Generate Ecitizen Number *&* ID Card.
- Enable Security Policy for `message` route to accept Requests only from `X-Twilio-Signature header` or `X-API-Key`
- Set `UPDATE_PASSWORD` as the only Required Action, remove `UPDATE_PHONE_NUMBER`
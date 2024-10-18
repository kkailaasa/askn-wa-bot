# User Registration Flow Guide

This document outlines the step-by-step process for user registration and authentication in our system.

## 1. Initial Authentication Attempt

1. The user provides their phone number.
2. The system checks if the phone number exists in Keycloak:
   - As a username
   - In the phoneNumber attribute of any user

3. Possible outcomes:
   a) If found: User is authenticated, and the process ends.
   b) If not found: Proceed to step 2.

## 2. Email Check

1. The system asks the user for their email address.
2. The system checks if the email exists in Keycloak.

3. Possible outcomes:
   a) If email exists: 
      - The phone number is added to the user's attributes in Keycloak.
      - The process ends with the user authenticated.
   b) If email doesn't exist: Proceed to step 3.

## 3. Account Creation

1. The system prompts the user for additional information:
   - First name
   - Last name
   - Gender
   - Country

2. A new user account is created in Keycloak with:
   - Username: Phone number
   - Attributes: Phone number, gender, country

3. The system stores the email (provided in step 2) temporarily.

## 4. Email Verification

1. The system triggers the send_email_otp endpoint to send an OTP (One-Time Password) to the email address provided earlier.
2. An OTP is generated and sent to the user's email.
3. The user enters the OTP.
4. The system verifies the OTP using the verify_email endpoint:
   - If correct: The email is added to the user's Keycloak account and marked as verified.
   - If incorrect: The user is prompted to try again (with rate limiting

## Additional Notes

- Rate limiting is applied to all steps to prevent abuse.
- Temporary data (like email during the registration process) is stored in Redis with an expiration time.
- A cleanup mechanism runs periodically to remove expired temporary data and old rate-limiting data from Redis.

This flow ensures a smooth user experience while maintaining security and preventing duplicate accounts. It allows for users who may have an email registered but not a phone number, and vice versa.

# eCitizen Registration Flow

## Overview

This document outlines the registration flow for the eCitizen system, detailing the steps from initial phone number check to email verification. The process is designed to handle both new user registrations and scenarios where users may have partial registrations or existing accounts.

## Flow Steps

### 1. Check Phone Number (`/check_phone`)

- **Input**: Phone number
- **Process**:
  - Check if the phone number exists in the system
  - If found, return user details
  - If not found, store phone number temporarily and proceed to email check
- **Outcome**:
  - User found: Return user details
  - User not found: Proceed to email check

### 2. Check Email (`/check_email`)

- **Input**: Phone number and email
- **Process**:
  - Verify that the phone number was checked in the previous step
  - Check if the email exists in the system
  - If email found, add phone attributes to the existing account
  - If email not found, store email along with phone details
- **Outcome**:
  - Existing user: Update account with phone details
  - New user: Proceed to account creation

### 3. Create Account (`/create_account`)

- **Input**: User details (phone, email, name, gender, country)
- **Process**:
  - Verify that previous steps were completed
  - Create a new user account in Keycloak with provided details
  - Include additional attributes like phone type and verification route
- **Outcome**:
  - Account created: Return user ID and prompt for email verification

### 4. Send Email OTP (`/send_email_otp`)

- **Input**: Email address
- **Process**:
  - Generate a one-time password (OTP)
  - Store the OTP with the email address
  - Send the OTP to the user's email
- **Outcome**:
  - OTP sent successfully: Inform user to check their email
  - Failed to send: Return error

### 5. Verify Email (`/verify_email`)

- **Input**: Email and OTP
- **Process**:
  - Verify the OTP against the stored value
  - If valid, mark the email as verified in Keycloak
- **Outcome**:
  - Email verified: Complete the registration process
  - Invalid OTP: Prompt user to try again

## Security Measures

- **Rate Limiting**: Implemented on sensitive endpoints to prevent abuse
- **API Key**: All endpoints require a valid API key for access
- **Temporary Data Storage**: User data is temporarily stored between steps for seamless flow
- **OTP Expiration**: Email verification OTPs are set to expire after a short period

## Error Handling

- Keycloak operation errors are caught and logged
- HTTP exceptions are raised with appropriate status codes and messages
- Logging is implemented throughout the flow for debugging and monitoring

## Notes

- The system is designed to handle WhatsApp-based registrations, as indicated by the `phoneType` and `verificationRoute` attributes
- The flow allows for adding phone numbers to existing accounts, facilitating user profile updates
- Email verification is a crucial step to ensure the validity of user contact information

This registration flow provides a robust and secure method for user onboarding, accommodating various scenarios and ensuring data integrity throughout the process.

## Codebase

- Endpoints Logic is handled by api.routes.py
- All Ecitizen Auth Functions is handled by services.ecitizen_auth.py
- Email Verification is handled by services.email_service.py
- Environmental Configurations are handled by core.config.py
 
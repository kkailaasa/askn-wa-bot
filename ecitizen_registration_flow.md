# eCitizen Registration Flow

## Overview

This document outlines the enhanced registration flow for the eCitizen system, detailing the steps from initial phone number check to email verification. The process handles multiple scenarios including new registrations, account merging, and profile updates.

## Flow Scenarios

### 1. New User Registration
- Check phone number (not found in system)
- Store phone number in temporary storage
- Check email (not found in system)
- Store email with phone details
- Create new account
- Send email verification OTP
- Verify email
- Complete registration

### 2. Existing Phone User Without Email
- Check phone number (found, but no email)
- Store user ID and phone number
- Check email
- Add email to existing account
- Send verification OTP
- Verify email
- Complete update

### 3. Existing Email User
- Check phone number (not found)
- Store phone number
- Check email (found)
- Add phone number to email account
- Complete update

### 4. Merging Accounts (Phone and Email Exist Separately)
- Check phone number (found)
- Check email (found in different account)
- Merge accounts:
  - Keep email account as primary
  - Transfer phone attributes
  - Disable phone-only account
- Complete merger

## Detailed Flow Steps

### 1. Check Phone Number (`/check_phone`)

- **Input**: Phone number
- **Process**:
  - Check username field for phone number
  - Check phoneNumber attribute
  - Store results in temporary storage if needed
- **Outcomes**:
  - User found with email: Return user details
  - User found without email: Store user ID, proceed to email check
  - User not found: Store phone number, proceed to email check

### 2. Check Email (`/check_email`)

- **Input**: Phone number and email
- **Process**:
  - Verify previous step completion
  - Check for existing email user
  - Check for phone user from previous step
  - Handle account merging if needed
- **Outcomes**:
  - Accounts merged: Return merged user details
  - Email added to phone account: Return updated user
  - Phone added to email account: Return updated user
  - Neither exists: Proceed to account creation

### 3. Create Account (`/create_account`)

- **Input**: Complete user details
- **Process**:
  - Verify previous steps completion
  - Create new Keycloak account
  - Set required attributes
  - Set UPDATE_PASSWORD action
- **Outcome**:
  - Account created: Return user ID and next step

### 4. Send Email OTP (`/send_email_otp`)

- **Input**: Email address
- **Process**:
  - Generate 6-digit OTP
  - Store OTP with 10-minute expiration
  - Send via SendGrid
- **Outcome**:
  - OTP sent: Success message
  - Failed to send: Error message

### 5. Verify Email (`/verify_email`)

- **Input**: Email and OTP
- **Process**:
  - Validate OTP
  - Mark email as verified
- **Outcome**:
  - Valid OTP: Mark email verified
  - Invalid OTP: Return error

## Security Measures

- **Rate Limiting**:
  - Create User: 100/hour
  - Add Email: 100/hour
  - Verify Email: 100/5 minutes
  - Messages: 100/5 minutes

- **Data Protection**:
  - Temporary data expires in 1 hour
  - OTPs expire in 10 minutes
  - API key required for all endpoints
  - WhatsApp verification for phone numbers
  - Email verification required

## Account Merging Rules

1. Email Account Priority:
   - Email account is always primary
   - Phone account is disabled after merge
   - All attributes are merged to email account

2. Data Preservation:
   - No data is deleted during merges
   - Phone account preserved for audit
   - All phone numbers transferred to primary account

## Codebase Structure

- **API Routes**: `api/routes.py`
  - Endpoint definitions
  - Flow control
  - Error handling

- **Authentication**: `services/ecitizen_auth.py`
  - Keycloak operations
  - User management
  - Account merging logic

- **Email Service**: `services/email_service.py`
  - OTP generation
  - Email sending
  - Verification logic

- **Configuration**: `core/config.py`
  - Environment settings
  - Rate limiting
  - Security parameters

## Error Handling

- Invalid request sequence
- Rate limit exceeded
- Invalid API key
- Keycloak operation errors
- Email sending failures
- OTP verification failures

## Notes

- WhatsApp is primary phone verification method
- Multiple phone numbers supported per account
- Email verification mandatory
- Account merging preserves all data
- Temporary storage using Redis
- Comprehensive logging implemented
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


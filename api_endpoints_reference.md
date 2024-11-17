# API Endpoints Reference

## 1. Check Phone Number
**Endpoint:** `/check_phone`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string"
}
```

**Response Scenarios:**
```json
// Scenario 1: User found with email
{
  "message": "User found",
  "user": {
    "id": "string",
    "username": "string",
    "email": "string",
    "enabled": true,
    "attributes": {}
  }
}

// Scenario 2: User found without email
{
  "message": "User found but email not set",
  "user": {
    "id": "string",
    "username": "string",
    "email": null,
    "enabled": true,
    "attributes": {}
  },
  "next_step": "check_email"
}

// Scenario 3: User not found
{
  "message": "User not found",
  "next_step": "check_email"
}
```

**Example curl command:**
```bash
curl -X POST "http://localhost:7262/check_phone" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{"phone_number": "+254712345678"}'
```

## 2. Check Email
**Endpoint:** `/check_email`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string",
  "email": "string"
}
```

**Response Scenarios:**
```json
// Scenario 1: Accounts merged (when both phone and email exist separately)
{
  "message": "Accounts merged successfully",
  "user": {
    "id": "string",
    "username": "string",
    "email": "string",
    "enabled": true,
    "attributes": {}
  }
}

// Scenario 2: Email added to existing phone account
{
  "message": "Email added to existing account",
  "user": {
    "id": "string",
    "username": "string",
    "email": "string",
    "enabled": true,
    "attributes": {}
  }
}

// Scenario 3: Phone added to existing email account
{
  "message": "Phone attributes added to existing account",
  "user": {
    "id": "string",
    "username": "string",
    "email": "string",
    "enabled": true,
    "attributes": {}
  }
}

// Scenario 4: New user creation needed
{
  "message": "User not found",
  "next_step": "create_account"
}
```

**Example curl command:**
```bash
curl -X POST "http://localhost:7262/check_email" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{"phone_number": "+254712345678", "email": "user@example.com"}'
```

## 3. Create Account
**Endpoint:** `/create_account`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string",
  "email": "string",
  "first_name": "string",
  "last_name": "string",
  "gender": "string",
  "country": "string"
}
```

**Response:**
```json
{
  "message": "User account created with UPDATE_PASSWORD action",
  "user_id": "string",
  "next_step": "verify_email"
}
```

**Example curl command:**
```bash
curl -X POST "http://localhost:7262/create_account" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{
       "phone_number": "+254712345678",
       "email": "user@example.com",
       "first_name": "John",
       "last_name": "Doe",
       "gender": "male",
       "country": "Kenya"
     }'
```

## 4. Send Email OTP
**Endpoint:** `/send_email_otp`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string",
  "email": "string"
}
```

**Response:**
```json
{
  "message": "OTP sent successfully"
}
```

**Example curl command:**
```bash
curl -X POST "http://localhost:7262/send_email_otp" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{"phone_number": "+254712345678", "email": "user@example.com"}'
```

## 5. Verify Email
**Endpoint:** `/verify_email`
**Method:** POST
**Request Body:**
```json
{
  "email": "string",
  "otp": "string"
}
```

**Response:**
```json
{
  "message": "Email verified successfully."
}
```

**Example curl command:**
```bash
curl -X POST "http://localhost:7262/verify_email" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{"email": "user@example.com", "otp": "123456"}'
```

## 6. Message Endpoint
**Endpoint:** `/message`
**Method:** POST
**Headers:**
- Content-Type: application/x-www-form-urlencoded
- X-Twilio-Signature: {twilio_signature}

**Body Parameters:**
| Parameter | Type   | Required | Description                    |
|-----------|--------|----------|--------------------------------|
| Body      | string | Yes      | The content of the message     |
| From      | string | Yes      | The sender's phone number      |

**Success Response:**
```json
{
  "message": "Message received and being processed."
}
```

**Example curl commands:**
```bash
# With Twilio Signature
curl -X POST "https://your-api-domain.com/message" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -H "X-Twilio-Signature: YOUR_TWILIO_SIGNATURE" \
     -d "Body=Hello, how are you?" \
     -d "From=+1234567890"

# Without Twilio Signature (for testing)
curl -X POST 'https://your-api-domain.com/message' \
  --data-urlencode 'To=whatsapp:+1800000000' \
  --data-urlencode 'From=whatsapp:+19000000000' \
  --data-urlencode 'Body=Hello, this is a test message from Twilio!'
```

**Fetching Info on E-Citizen**
```bash
# Get user info by email
curl -X POST http://localhost:7262/get_user_info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "identifier": "user@example.com",
    "identifier_type": "email"
  }'

# Get user info by phone
curl -X POST http://localhost:7262/get_user_info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{
    "identifier": "+1234567890",
    "identifier_type": "phone"
  }'


```

## Error Responses

### Rate Limit Exceeded
```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```
Status Code: 429

### Invalid API Key
```json
{
  "detail": "Could not validate API key"
}
```
Status Code: 403

### Invalid Request Sequence
```json
{
  "detail": "Invalid request sequence"
}
```
Status Code: 400

### Internal Server Error
```json
{
  "detail": "Internal server error"
}
```
Status Code: 500

## Rate Limits
- Create User: 100 requests per hour
- Add Email: 100 requests per hour
- Verify Email: 100 requests per 5 minutes
- Message Processing: 100 messages per 5 minutes

## Security Notes
- All endpoints require API key authentication
- Twilio webhook validation is enforced on the message endpoint
- OTPs expire after 10 minutes
- Temporary data expires after 1 hour
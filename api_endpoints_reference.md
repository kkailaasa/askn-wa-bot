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
**Example curl command:**
```bash
curl -X POST "http://localhost:7262/verify_email" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your_api_key_here" \
     -d '{"email": "user@example.com", "otp": "123456"}'
```
---

Note: Replace `your_api_key_here` with the actual API key, and adjust the localhost URL if your server is running on a different host or port.

---

## Endpoint: `/message`
**Method:** POST

## Description
This endpoint handles incoming messages from Twilio. It processes the message, generates a response using the chat service, and sends the response back to the user via Twilio.

## Request

### Headers
- `Content-Type: application/x-www-form-urlencoded`
- `X-Twilio-Signature: {twilio_signature}` (Used for request validation)

### Body Parameters
| Parameter | Type   | Required | Description                    |
|-----------|--------|----------|--------------------------------|
| Body      | string | Yes      | The content of the message     |
| From      | string | Yes      | The sender's phone number      |

## Response

### Success Response
**Code:** 202 ACCEPTED
**Content:**
```json
{
  "message": "Message received and being processed."
}
```

### Error Responses

#### Rate Limit Exceeded
**Code:** 429 TOO MANY REQUESTS
**Content:**
```json
{
  "message": "Rate limit exceeded. Please try again later."
}
```

#### Internal Server Error
**Code:** 500 INTERNAL SERVER ERROR
**Content:**
```json
{
  "message": "An error occurred while processing your message."
}
```

## Notes
- This endpoint is specifically designed to work with Twilio's webhook system.
- The incoming request is validated to ensure it's from Twilio.
- Rate limiting is applied to prevent abuse.
- Message processing is handled asynchronously to provide a quick response to Twilio.
- The actual response to the user's message is sent separately via Twilio after processing.

## Example curl command with Twilio Signature 
```bash
curl -X POST "https://your-api-domain.com/message" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -H "X-Twilio-Signature: YOUR_TWILIO_SIGNATURE" \
     -d "Body=Hello, how are you?" \
     -d "From=+1234567890"
```

## Example curl command without Twilio Signature 
```bash
curl -X POST 'https://your-api-domain.com/message' \
  --data-urlencode 'To=whatsapp:+1800000000' \
  --data-urlencode 'From=whatsapp:+19000000000' \
  --data-urlencode 'Body=Hello, this is a test message from Twilio!'
```

Note: Replace `YOUR_TWILIO_SIGNATURE` with the actual signature provided by Twilio. This signature is used to validate that the request is genuinely from Twilio.
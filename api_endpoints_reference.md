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

Note: Replace `your_api_key_here` with the actual API key, and adjust the localhost URL if your server is running on a different host or port.
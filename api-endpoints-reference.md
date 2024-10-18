# API Endpoints Reference

## 1. Authenticate User
**Endpoint:** `/authenticate`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string"
}
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

## 3. Create Account
**Endpoint:** `/create_account`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string",
  "first_name": "string",
  "last_name": "string",
  "gender": "string",
  "country": "string"
}
```

## 4. Send Email OTP
**Endpoint:** `/send_email_otp`
**Method:** POST
**Request Body:**
```json
{
  "email": "string"
}
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
## 6. Process Message (Twilio Webhook)
**Endpoint:** `/message`
**Method:** POST
**Form Data:**
```json
- `Body`: The message body (string)
- `From`: The sender's phone number (string)
```

### *Following are extra endpoints which wll not be relevant for WA Ecitizen Workflows*

## 7. Get User by Email
**Endpoint:** `/get_user_by_email`
**Method:** POST
**Request Body:**
```json
{
  "email": "string"
}
```

## 8. Get User by Phone
**Endpoint:** `/get_user_by_phone`
**Method:** POST
**Request Body:**
```json
{
  "phone_number": "string"
}
```

Note: All endpoints except `/message` require an API key to be included in the request header as `X-API-Key`.

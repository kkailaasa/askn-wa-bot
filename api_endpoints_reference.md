# API Endpoints Reference

## General Information

### Authentication
All endpoints require an API key passed via the `X-API-Key` header.

### Response Format
All endpoints return responses in the following format:
```json
{
    "status": "success|failed|pending|blocked|retry_needed",
    "message": "string",
    "error_code": "string (optional)",
    "data": {}, // Optional response data
    "next_action": "string (optional)",
    "retry_after": "number (optional)",
    "error_context": {} // Optional error details
}
```

### Rate Limiting
Rate limits are implemented for all endpoints using Redis. Headers returned include:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests in window
- `X-RateLimit-Reset`: Time until limit resets (seconds)

## Endpoints

### 1. Check Phone Number
**Endpoint:** `/api/check_phone`  
**Method:** POST  
**Rate Limit:** 10 requests per 300 seconds per phone number

**Request Body:**
```json
{
    "phone_number": "string" // Format: +1234567890 or whatsapp:+1234567890
}
```

**Success Responses:**
```json
// User found with email
{
    "status": "success",
    "message": "User found",
    "data": {
        "user": {
            "id": "string",
            "username": "string",
            "email": "string",
            "enabled": true,
            "attributes": {}
        }
    }
}

// User found without email
{
    "status": "success",
    "message": "User found but email not set",
    "data": {
        "user": {
            "id": "string",
            "username": "string",
            "email": null,
            "attributes": {}
        }
    },
    "next_action": "check_email"
}

// User not found
{
    "status": "success",
    "message": "User not found",
    "next_action": "check_email"
}
```

### 2. Check Email
**Endpoint:** `/api/check_email`  
**Method:** POST  
**Rate Limit:** 20 requests per 300 seconds per email

**Request Body:**
```json
{
    "phone_number": "string",
    "email": "string"
}
```

**Success Response:**
```json
{
    "status": "success",
    "message": "Email check completed",
    "data": {
        "existing_phone_user": boolean,
        "existing_email_user": boolean
    },
    "next_action": "create_account"
}
```

### 3. Create Account
**Endpoint:** `/api/create_account`  
**Method:** POST  
**Rate Limit:** 10 requests per 60 seconds per IP

**Request Body:**
```json
{
    "phone_number": "string",
    "email": "string",
    "first_name": "string",
    "last_name": "string",
    "gender": "string", // male|female|other|prefer_not_to_say
    "country": "string" // ISO 2-letter code
}
```

**Success Response:**
```json
{
    "status": "success",
    "message": "Account created successfully",
    "data": {
        "user_id": "string",
        "verification_pending": true
    },
    "next_action": "send_email_otp"
}
```

### 4. Send Email OTP
**Endpoint:** `/api/send_email_otp`  
**Method:** POST  
**Rate Limit:** 3 requests per 300 seconds per email

**Request Body:**
```json
{
    "phone_number": "string",
    "email": "string"
}
```

**Success Response:**
```json
{
    "status": "success",
    "message": "OTP sent successfully",
    "data": {
        "email": "string"
    },
    "next_action": "verify_email"
}
```

### 5. Verify Email
**Endpoint:** `/api/verify_email`  
**Method:** POST  
**Rate Limit:** 5 attempts per email within OTP validity period (10 minutes)

**Request Body:**
```json
{
    "email": "string",
    "otp": "string"
}
```

**Success Response:**
```json
{
    "status": "success",
    "message": "Email verified successfully",
    "data": {
        "email": "string",
        "verified": true
    }
}
```

### 6. Message Processing
**Endpoint:** `/api/message`  
**Method:** POST  
**Rate Limit:** 70 messages per second per Twilio number  
**Content-Type:** application/x-www-form-urlencoded

**Request Parameters:**
- `Body`: string (required) - Message content
- `From`: string (required) - Sender's WhatsApp number

**Success Response:**
```json
{
    "status": "success",
    "message": "Message processed successfully",
    "data": {
        "conversation_id": "string",
        "timestamp": "string"
    }
}
```

### 7. Get User Info
**Endpoint:** `/api/get_user_info`  
**Method:** POST  
**Rate Limit:** 20 requests per 300 seconds per identifier

**Request Body:**
```json
{
    "identifier": "string",
    "identifier_type": "email|phone"
}
```

**Success Response:**
```json
{
    "username": "string",
    "email": "string",
    "enabled": boolean,
    "firstName": "string",
    "lastName": "string",
    "attributes": {
        "phoneType": "string",
        "phoneNumber": "string",
        "gender": "string",
        "phoneVerified": "string",
        "country": "string",
        "verificationRoute": "string"
    },
    "message": "User information retrieved successfully"
}
```

### 8. Health Check
**Endpoint:** `/api/health`  
**Method:** GET  
**No authentication required**

**Response:**
```json
{
    "status": "healthy|degraded|unhealthy",
    "timestamp": "string",
    "version": "string",
    "components": {
        "redis": {
            "status": "healthy|unhealthy",
            "latency_ms": number
        },
        "keycloak": {
            "status": "healthy|unhealthy",
            "latency_ms": number
        }
    }
}
```

## Load Balancer Endpoints

### 1. Signup Redirect
**Endpoint:** `/api/lb/signup`  
**Method:** GET  
**Rate Limit:** 10 requests per 60 seconds per IP

**Response:** Redirects to WhatsApp chat with selected number

### 2. Load Statistics
**Endpoint:** `/api/lb/load-stats`  
**Method:** GET  
**Rate Limit:** 30 requests per 60 seconds per IP

**Response:**
```json
{
    "whatsapp:+1234567890": number, // Current messages/second
    "whatsapp:+0987654321": number
}
```

## Error Codes and Messages

### Common Error Codes
- `INVALID_PHONE`: Invalid phone number format
- `INVALID_EMAIL`: Invalid email format
- `INVALID_DATA`: Invalid input data
- `VALIDATION_ERROR`: Input validation failed
- `SEQUENCE_VIOLATION`: Invalid operation sequence
- `RATE_LIMIT`: Rate limit exceeded
- `KEYCLOAK_ERROR`: Authentication service error
- `EMAIL_ERROR`: Email service error
- `SYSTEM_ERROR`: Internal server error
- `TIMEOUT`: Operation timed out
- `DATA_NOT_FOUND`: Requested data not found
- `MAX_ATTEMPTS_EXCEEDED`: Maximum retry attempts reached

### Error Response Format
```json
{
    "status": "failed",
    "message": "Error description",
    "error_code": "ERROR_CODE",
    "retry_after": number, // Optional, for rate limits
    "error_context": {
        "timestamp": "string",
        "details": {},
        "operation": "string"
    }
}
```

## Sequence Management
The API enforces strict operation sequences:
1. check_phone
2. check_email
3. create_account
4. send_email_otp
5. verify_email

Each step must be completed in order, and data consistency is maintained across steps.

## Security Features
- API key validation on all endpoints
- Rate limiting per IP and identifier
- Request tracking with X-Request-ID
- Sequence state expiration (1 hour)
- OTP expiration (10 minutes)
- Maximum OTP verification attempts (3)
- Load balancer thresholds and alerts
- Comprehensive error logging and monitoring

## Monitoring and Logging
All endpoints include:
- Request/Response logging
- Error tracking
- Performance metrics
- Load statistics
- Health monitoring
- Rate limit tracking

Headers returned include:
- `X-Request-ID`: Request identifier
- `X-Process-Time`: Processing time in seconds

## Development Notes
Base URL for development: `http://localhost:7262/api/`
All timestamps are in ISO 8601 format and UTC timezone.
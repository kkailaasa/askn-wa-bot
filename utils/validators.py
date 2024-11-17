# utils/validators.py

import re
from typing import Union

def validate_phone_format(phone: str) -> bool:
    """
    Validate phone number format.
    Accepts formats: +1234567890, 1234567890, whatsapp:+1234567890
    """
    # Remove whatsapp: prefix if present
    phone = phone.replace("whatsapp:", "").strip()

    # Remove + if present
    phone = phone.replace("+", "")

    # Check if it's all digits and proper length
    return (
        phone.isdigit() and
        len(phone) >= 10 and
        len(phone) <= 15
    )

def validate_email_format(email: str) -> bool:
    """
    Validate email format using regex
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_name_format(name: str) -> bool:
    """
    Validate name format
    """
    # Allow letters, spaces, hyphens, and apostrophes
    pattern = r'^[a-zA-Z\s\'-]+$'
    return bool(re.match(pattern, name)) and len(name) <= 50

def validate_gender(gender: str) -> bool:
    """
    Validate gender format
    """
    valid_genders = ['male', 'female', 'other', 'prefer_not_to_say']
    return gender.lower() in valid_genders

def validate_country(country: str) -> bool:
    """
    Validate country format (ISO 2-letter code)
    """
    return len(country) == 2 and country.isalpha()
import os
      
DB_HOST = os.getenv('DB_HOST') or "127.0.0.1"
DB_SCHEMA = os.getenv('DB_SCHEMA') or "program_consent"
DB_USER = os.getenv('DB_USER') or "program_consent"
DB_PASSWORD = os.getenv('DB_PASSWORD') or "program_consent"
DB_PORT = os.getenv('DB_PORT') or '3306'

print("================")
print("DB_HOST: " + DB_HOST)
print("DB_SCHEMA: " + DB_SCHEMA)
print("DB_USER: " + DB_USER)
print("DB_PASSWORD: " + DB_PASSWORD)
print("DB_PORT: " + DB_PORT)
print("================")

# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': DB_SCHEMA,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'charset': 'utf8mb4'  # This is the relevant line
        },
    }
}
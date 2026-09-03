"""
settings.py - EXAMPLE FILE
Copy this to settings.py and fill in your secrets
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ✅ Replace with your actual secret
SECRET_KEY = 'django-insecure-replace-this-with-your-secret'

# ✅ Set to False in production
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'quickbooks',
    'payments',
    'loans',
    'applications',
    'audit',
    # ... other apps
]

# QuickBooks Settings - Replace with your credentials
QUICKBOOKS = {
    'CLIENT_ID': os.environ.get('QUICKBOOKS_CLIENT_ID', 'your-client-id'),
    'CLIENT_SECRET': os.environ.get('QUICKBOOKS_CLIENT_SECRET', 'your-client-secret'),
    'REDIRECT_URI': os.environ.get('QUICKBOOKS_REDIRECT_URI', 'http://localhost:8000/quickbooks/callback/'),
    'ENVIRONMENT': os.environ.get('QUICKBOOKS_ENVIRONMENT', 'sandbox'),
    'SCOPES': 'com.intuit.quickbooks.accounting',
}

QUICKBOOKS_AUTH_URLS = {
    'sandbox': {
        'auth_url': 'https://appcenter.intuit.com/connect/oauth2',
        'token_url': 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
        'api_url': 'https://sandbox-quickbooks.api.intuit.com/v3/company/',
    },
    'production': {
        'auth_url': 'https://appcenter.intuit.com/connect/oauth2',
        'token_url': 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
        'api_url': 'https://quickbooks.api.intuit.com/v3/company/',
    }
}

# Database - Use environment variables
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'your_db_name'),
        'USER': os.environ.get('DB_USER', 'your_db_user'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'your_db_password'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# ... rest of your non-sensitive settings ...

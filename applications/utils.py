# applications/utils.py
import uuid
from datetime import datetime

def generate_customer_id(first_name, last_name):
    """Generate a unique customer ID like: KD20260825143015"""
    initials = f"{first_name[0]}{last_name[0]}".upper()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{initials}{timestamp}"
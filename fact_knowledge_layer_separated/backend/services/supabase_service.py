"""Optional Supabase sync. Local SQLite remains the offline fallback."""
import os

def configured(): return bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

def get_client():
    if not configured(): return None
    from supabase import create_client
    return create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

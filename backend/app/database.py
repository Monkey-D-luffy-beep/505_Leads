from supabase import create_client, Client
from app.config import settings


def get_supabase_client() -> Client:
    """Initialize and return the Supabase client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


supabase: Client = get_supabase_client()

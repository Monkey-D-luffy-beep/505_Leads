from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_supabase_client() -> Client:
    """Initialize and return the Supabase client (lazy singleton)."""
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


class _LazyClient:
    """Proxy that defers Supabase client creation until first attribute access."""
    def __getattr__(self, name):
        return getattr(get_supabase_client(), name)


supabase: Client = _LazyClient()  # type: ignore

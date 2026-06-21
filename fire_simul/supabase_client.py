from __future__ import annotations

from supabase import Client, create_client

from .config import get_supabase_settings


def get_client(service_role: bool = False) -> Client:
    settings = get_supabase_settings(service_role=service_role)
    return create_client(settings.url, settings.key)

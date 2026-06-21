from __future__ import annotations

from dataclasses import dataclass
import os


TRACKED_SYMBOLS = ("TQQQ", "QLD", "SPYM", "BOXX")
FX_SYMBOL = "KRW=X"
FX_PAIR = "USD/KRW"
START_DATE = "2026-06-15"
MARKET_DATA_START_DATE = "2025-06-01"
MONTHLY_WITHDRAWAL_DAY = 15
MONTHLY_WITHDRAWAL_WON = 3_000_000


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    key: str


def get_supabase_settings(service_role: bool = False) -> SupabaseSettings:
    url = os.environ.get("SUPABASE_URL", "")
    key_name = "SUPABASE_SERVICE_ROLE_KEY" if service_role else "SUPABASE_ANON_KEY"
    key = os.environ.get(key_name) or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "Supabase settings are missing. Set SUPABASE_URL and "
            f"{key_name} in environment variables or Streamlit secrets."
        )
    return SupabaseSettings(url=url, key=key)

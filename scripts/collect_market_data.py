from __future__ import annotations

import argparse
from datetime import date, timedelta
import os
import sys

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fire_simul.config import MARKET_DATA_START_DATE, TRACKED_SYMBOLS
from fire_simul.market_data import fetch_usd_krw, fetch_yfinance_closes, upsert_market_data
from fire_simul.supabase_client import get_client


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Collect ETF closes and USD/KRW into Supabase.")
    parser.add_argument("--start", default=MARKET_DATA_START_DATE)
    parser.add_argument("--end", default=(date.today() + timedelta(days=1)).isoformat())
    args = parser.parse_args()

    client = get_client(service_role=True)
    prices = fetch_yfinance_closes(TRACKED_SYMBOLS, start=args.start, end=args.end)
    rates = fetch_usd_krw(start=args.start, end=args.end)
    if prices.empty:
        print("No ETF price rows were collected. This is usually a temporary yfinance rate limit.")
    if rates.empty:
        print("No USD/KRW rows were collected. This is usually a temporary yfinance rate limit.")
    price_count, rate_count = upsert_market_data(client, prices, rates)
    print(f"Upserted {price_count} market price rows and {rate_count} exchange-rate rows.")


if __name__ == "__main__":
    main()

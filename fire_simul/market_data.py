from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf

from .config import FX_PAIR, FX_SYMBOL, TRACKED_SYMBOLS


def fetch_yfinance_closes(
    symbols: Iterable[str] = TRACKED_SYMBOLS,
    start: str | date | None = None,
    end: str | date | None = None,
) -> pd.DataFrame:
    start_date = pd.to_datetime(start or "2026-06-15").date()
    end_date = pd.to_datetime(end or (date.today() + timedelta(days=1))).date()
    tickers = list(symbols)
    data = yf.download(
        tickers=tickers,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    rows: list[dict[str, object]] = []
    for symbol in tickers:
        if len(tickers) == 1:
            close_series = data["Close"]
        else:
            close_series = data[(symbol, "Close")]
        for trade_date, close in close_series.dropna().items():
            rows.append(
                {
                    "trade_date": pd.Timestamp(trade_date).date().isoformat(),
                    "symbol": symbol,
                    "close": round(float(close), 6),
                    "currency": "USD",
                    "source": "yfinance",
                }
            )
    return pd.DataFrame(rows)


def fetch_usd_krw(start: str | date | None = None, end: str | date | None = None) -> pd.DataFrame:
    start_date = pd.to_datetime(start or "2026-06-15").date()
    end_date = pd.to_datetime(end or (date.today() + timedelta(days=1))).date()
    data = yf.download(
        tickers=FX_SYMBOL,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        auto_adjust=False,
        progress=False,
    )
    close = data["Close"].dropna()
    return pd.DataFrame(
        [
            {
                "rate_date": pd.Timestamp(rate_date).date().isoformat(),
                "pair": FX_PAIR,
                "rate": round(float(rate), 6),
                "source": "yfinance",
            }
            for rate_date, rate in close.items()
        ]
    )


def load_market_prices(client, start: str = "2026-06-15") -> pd.DataFrame:
    response = (
        client.table("market_prices")
        .select("trade_date,symbol,close,currency,source")
        .gte("trade_date", start)
        .order("trade_date")
        .execute()
    )
    return pd.DataFrame(response.data or [])


def load_exchange_rates(client, start: str = "2026-06-15") -> pd.DataFrame:
    response = (
        client.table("exchange_rates")
        .select("rate_date,pair,rate,source")
        .gte("rate_date", start)
        .order("rate_date")
        .execute()
    )
    return pd.DataFrame(response.data or [])


def upsert_market_data(client, prices: pd.DataFrame, rates: pd.DataFrame) -> tuple[int, int]:
    price_rows = prices.to_dict(orient="records")
    rate_rows = rates.to_dict(orient="records")
    if price_rows:
        client.table("market_prices").upsert(
            price_rows,
            on_conflict="trade_date,symbol,source",
        ).execute()
    if rate_rows:
        client.table("exchange_rates").upsert(
            rate_rows,
            on_conflict="rate_date,pair,source",
        ).execute()
    return len(price_rows), len(rate_rows)


def latest_trade_date(prices: pd.DataFrame) -> str | None:
    if prices.empty:
        return None
    return str(prices["trade_date"].max())

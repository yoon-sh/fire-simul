from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
import time
from typing import Iterable

import pandas as pd
import requests
import yfinance as yf

from .config import FX_PAIR, FX_SYMBOL, TRACKED_SYMBOLS


def _download_with_retry(
    ticker: str,
    start_date: date,
    end_date: date,
    attempts: int = 2,
    delay_seconds: int = 5,
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            data = yf.download(
                tickers=ticker,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=10,
            )
            if not data.empty:
                return data
            print(f"No data returned for {ticker} on attempt {attempt}.")
        except Exception as exc:  # yfinance raises different exception classes by version.
            last_error = exc
            print(f"Download failed for {ticker} on attempt {attempt}: {exc}")
        if attempt < attempts:
            time.sleep(delay_seconds)
    if last_error:
        print(f"Giving up on {ticker}: {last_error}")
    return pd.DataFrame()


def _close_series(data: pd.DataFrame, ticker: str) -> pd.Series:
    if data.empty:
        return pd.Series(dtype="float64")
    if isinstance(data.columns, pd.MultiIndex):
        if (ticker, "Close") in data.columns:
            return data[(ticker, "Close")].dropna()
        if ("Close", ticker) in data.columns:
            return data[("Close", ticker)].dropna()
    if "Close" in data.columns:
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            first_column = close.columns[0]
            return close[first_column].dropna()
        return close.dropna()
    return pd.Series(dtype="float64")


def _fetch_stooq_close(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    stooq_symbol = f"{symbol.lower()}.us"
    url = (
        "https://stooq.com/q/d/l/"
        f"?s={stooq_symbol}&d1={start_date:%Y%m%d}&d2={end_date:%Y%m%d}&i=d"
    )
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = pd.read_csv(StringIO(response.text))
    except Exception as exc:
        print(f"Stooq fallback failed for {symbol}: {exc}")
        return pd.DataFrame()

    if data.empty or "Date" not in data.columns or "Close" not in data.columns:
        print(f"Stooq fallback returned no usable rows for {symbol}.")
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp(row["Date"]).date().isoformat(),
                "symbol": symbol,
                "close": round(float(row["Close"]), 6),
                "currency": "USD",
                "source": "stooq",
            }
            for _, row in data.dropna(subset=["Date", "Close"]).iterrows()
        ]
    )


def fetch_yfinance_closes(
    symbols: Iterable[str] = TRACKED_SYMBOLS,
    start: str | date | None = None,
    end: str | date | None = None,
) -> pd.DataFrame:
    start_date = pd.to_datetime(start or "2026-06-15").date()
    end_date = pd.to_datetime(end or (date.today() + timedelta(days=1))).date()
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        data = _download_with_retry(symbol, start_date, end_date)
        close_series = _close_series(data, symbol)
        if close_series.empty:
            fallback = _fetch_stooq_close(symbol, start_date, end_date)
            rows.extend(fallback.to_dict(orient="records"))
        else:
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
    data = _download_with_retry(FX_SYMBOL, start_date, end_date)
    close = _close_series(data, FX_SYMBOL)
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

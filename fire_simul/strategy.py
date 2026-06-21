from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import pandas as pd

from .config import MONTHLY_WITHDRAWAL_DAY, MONTHLY_WITHDRAWAL_WON, START_DATE


INITIAL_QLD_VALUE = 20_000_000
QLD_ANNUAL_CONTRIBUTION = 20_000_000
QLD_CONTRIBUTION_CAP = 80_000_000
QLD_RESET_TRIGGER_VALUE = 85_000_000
QLD_RESET_KEEP_VALUE = 20_000_000
HIGH_BOXX_FLOOR = 100_000_000
LOW_BOXX_FLOOR = 36_000_000
BOXX_FLOOR_THRESHOLD = 150_000_000


@dataclass
class Portfolio:
    owner_id: str
    tqqq_value: float
    qld_value: float
    qld_cash_value: float
    spym_value: float
    boxx_value: float
    monthly_withdrawal: float = MONTHLY_WITHDRAWAL_WON
    cumulative_withdrawal: float = 0
    strategy_state: str = "BELOW_200DMA"
    qld_principal: float = INITIAL_QLD_VALUE

    @property
    def total_assets(self) -> float:
        return self.tqqq_value + self.qld_value + self.qld_cash_value + self.spym_value + self.boxx_value

    @property
    def boxx_floor(self) -> float:
        return HIGH_BOXX_FLOOR if self.total_assets >= BOXX_FLOOR_THRESHOLD else LOW_BOXX_FLOOR


def default_portfolios(couple_initial_assets: int) -> tuple[Portfolio, Portfolio]:
    per_person = couple_initial_assets / 2
    base = per_person - INITIAL_QLD_VALUE
    tqqq = round(base * 0.45)
    spym = round(base * 0.25)
    boxx = round(per_person - INITIAL_QLD_VALUE - tqqq - spym)
    return (
        Portfolio("self", tqqq, INITIAL_QLD_VALUE, 0, spym, boxx),
        Portfolio("spouse", tqqq, INITIAL_QLD_VALUE, 0, spym, boxx),
    )


def to_market_days(prices: pd.DataFrame, rates: pd.DataFrame | None = None) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    clean_prices = prices.copy()
    clean_prices["trade_date"] = pd.to_datetime(clean_prices["trade_date"]).dt.date.astype(str)
    clean_prices["close"] = pd.to_numeric(clean_prices["close"], errors="coerce")
    source_priority = {"yfinance": 0, "stooq": 1}
    clean_prices["source_priority"] = clean_prices["source"].map(source_priority).fillna(9)
    clean_prices = (
        clean_prices.dropna(subset=["trade_date", "symbol", "close"])
        .sort_values(["trade_date", "symbol", "source_priority"])
        .drop_duplicates(["trade_date", "symbol"], keep="first")
    )
    pivot = clean_prices.pivot_table(index="trade_date", columns="symbol", values="close", aggfunc="last")
    pivot = pivot.dropna(subset=["TQQQ", "QLD", "SPYM", "BOXX"]).sort_index()
    pivot["TQQQ_MA200"] = pivot["TQQQ"].rolling(200, min_periods=200).mean()
    if rates is not None and not rates.empty:
        rate_map = rates.drop_duplicates("rate_date").set_index("rate_date")["rate"]
        pivot["USD_KRW"] = pivot.index.to_series().map(rate_map).ffill().bfill()
    else:
        pivot["USD_KRW"] = 1
    pivot = pivot.dropna(subset=["TQQQ_MA200"])
    return pivot.reset_index()


def _apply_market_drift(portfolio: Portfolio, previous: pd.Series, current: pd.Series) -> Portfolio:
    return replace(
        portfolio,
        tqqq_value=round(portfolio.tqqq_value * current["TQQQ"] / previous["TQQQ"]),
        qld_value=round(portfolio.qld_value * current["QLD"] / previous["QLD"]),
        spym_value=round(portfolio.spym_value * current["SPYM"] / previous["SPYM"]),
        boxx_value=round(portfolio.boxx_value * current["BOXX"] / previous["BOXX"]),
    )


def _process_owner(portfolio: Portfolio, previous: pd.Series, current: pd.Series, is_first_trading_day_of_year: bool) -> Portfolio:
    p = replace(portfolio)
    if pd.isna(previous["TQQQ_MA200"]) or pd.isna(current["TQQQ_MA200"]):
        return p
    cross_down = previous["TQQQ"] > previous["TQQQ_MA200"] and current["TQQQ"] <= current["TQQQ_MA200"]
    cross_up = previous["TQQQ"] <= previous["TQQQ_MA200"] and current["TQQQ"] > current["TQQQ_MA200"]

    if cross_down:
        p.boxx_value += p.tqqq_value
        p.qld_cash_value += p.qld_value
        p.tqqq_value = 0
        p.qld_value = 0
        p.strategy_state = "EXIT_COMPLETED"
    elif cross_up:
        available_tqqq = max(p.boxx_value - p.boxx_floor, 0)
        available_qld = p.qld_cash_value
        p.boxx_value -= available_tqqq
        p.tqqq_value += available_tqqq
        p.qld_cash_value = 0
        p.qld_value += available_qld
        # TODO: This Streamlit preview applies re-entry in one day. The TypeScript engine has the exact 3-day split logic.
        p.strategy_state = "ENTRY_VALID"

    if (
        is_first_trading_day_of_year
        and current["TQQQ"] > current["TQQQ_MA200"]
        and p.strategy_state == "ENTRY_VALID"
        and p.tqqq_value >= QLD_ANNUAL_CONTRIBUTION
        and p.qld_principal < QLD_CONTRIBUTION_CAP
    ):
        p.tqqq_value -= QLD_ANNUAL_CONTRIBUTION
        p.qld_value += QLD_ANNUAL_CONTRIBUTION
        p.qld_principal += QLD_ANNUAL_CONTRIBUTION

    if (
        p.qld_principal >= QLD_CONTRIBUTION_CAP
        and p.qld_value >= QLD_RESET_TRIGGER_VALUE
        and current["TQQQ"] > current["TQQQ_MA200"]
        and p.strategy_state == "ENTRY_VALID"
    ):
        move_amount = p.qld_value - QLD_RESET_KEEP_VALUE
        p.qld_value = QLD_RESET_KEEP_VALUE
        p.tqqq_value += move_amount
        p.qld_principal = QLD_RESET_KEEP_VALUE

    current_date = pd.to_datetime(current["trade_date"]).date()
    if current_date.day == MONTHLY_WITHDRAWAL_DAY:
        if p.boxx_value >= p.monthly_withdrawal:
            p.boxx_value -= p.monthly_withdrawal
            p.cumulative_withdrawal += p.monthly_withdrawal
        # TODO: Record withdrawal failure rows after transaction persistence is added to the Python path.

    return p


def run_streamlit_simulation(prices: pd.DataFrame, rates: pd.DataFrame, couple_initial_assets: int) -> pd.DataFrame:
    market = to_market_days(prices, rates)
    if market.empty:
        return pd.DataFrame()
    market = market[market["trade_date"] >= START_DATE].reset_index(drop=True)
    if market.empty:
        return pd.DataFrame()

    self_p, spouse_p = default_portfolios(couple_initial_assets)
    rows: list[dict[str, object]] = []

    for index, current in market.iterrows():
        previous = market.iloc[max(index - 1, 0)]
        if index > 0:
            self_p = _apply_market_drift(self_p, previous, current)
            spouse_p = _apply_market_drift(spouse_p, previous, current)
        is_first_trading_day = index > 0 and str(current["trade_date"])[:4] != str(previous["trade_date"])[:4]
        if index > 0:
            self_p = _process_owner(self_p, previous, current, is_first_trading_day)
            spouse_p = _process_owner(spouse_p, previous, current, is_first_trading_day)

        rows.append(
            {
                "date": current["trade_date"],
                "self_total": round(self_p.total_assets),
                "spouse_total": round(spouse_p.total_assets),
                "couple_total": round(self_p.total_assets + spouse_p.total_assets),
                "tqqq_value": round(self_p.tqqq_value + spouse_p.tqqq_value),
                "qld_value": round(self_p.qld_value + spouse_p.qld_value),
                "qld_cash_value": round(self_p.qld_cash_value + spouse_p.qld_cash_value),
                "spym_value": round(self_p.spym_value + spouse_p.spym_value),
                "boxx_value": round(self_p.boxx_value + spouse_p.boxx_value),
                "growth_assets": round(self_p.tqqq_value + spouse_p.tqqq_value + self_p.qld_value + spouse_p.qld_value),
                "defense_assets": round(self_p.spym_value + spouse_p.spym_value + self_p.boxx_value + spouse_p.boxx_value),
                "self_boxx": round(self_p.boxx_value),
                "spouse_boxx": round(spouse_p.boxx_value),
                "self_withdrawal": round(self_p.cumulative_withdrawal),
                "spouse_withdrawal": round(spouse_p.cumulative_withdrawal),
                "couple_withdrawal": round(self_p.cumulative_withdrawal + spouse_p.cumulative_withdrawal),
                "tqqq_close": current["TQQQ"],
                "tqqq_ma200": current["TQQQ_MA200"],
            }
        )

    return pd.DataFrame(rows)

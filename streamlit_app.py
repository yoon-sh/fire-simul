from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from fire_simul.config import MONTHLY_WITHDRAWAL_DAY, START_DATE
from fire_simul.market_data import latest_trade_date, load_exchange_rates, load_market_prices
from fire_simul.strategy import run_streamlit_simulation
from fire_simul.supabase_client import get_client


load_dotenv()

st.set_page_config(
    page_title="FIRE 자산운용 시뮬레이터",
    page_icon="🔥",
    layout="wide",
)


def won(value: float | int) -> str:
    return f"{round(value):,}원"


@st.cache_data(ttl=600)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    client = get_client(service_role=False)
    prices = load_market_prices(client, START_DATE)
    rates = load_exchange_rates(client, START_DATE)
    return prices, rates


st.title("FIRE 자산운용 시뮬레이터")
st.caption("Supabase에 저장된 실제 종가 데이터를 읽어 매일 FIRE 가능성을 갱신합니다.")

with st.sidebar:
    st.header("설정")
    scenario = st.selectbox(
        "부부 합산 초기자산",
        options=[900_000_000, 1_200_000_000, 1_500_000_000],
        format_func=lambda value: f"{value // 100_000_000}억 원",
        index=1,
    )
    st.info(f"생활비 인출일은 매월 {MONTHLY_WITHDRAWAL_DAY}일입니다.")
    if st.button("데이터 새로고침"):
        st.cache_data.clear()

try:
    prices_df, rates_df = load_data()
except Exception as exc:
    st.error("Supabase 연결 정보를 찾을 수 없습니다.")
    st.code(
        "SUPABASE_URL, SUPABASE_ANON_KEY를 Streamlit secrets 또는 .env에 설정하세요.",
        language="text",
    )
    st.exception(exc)
    st.stop()

if prices_df.empty:
    st.warning("아직 Supabase에 종가 데이터가 없습니다. GitHub Actions 또는 수집 스크립트를 먼저 실행하세요.")
    st.stop()

latest = latest_trade_date(prices_df)
simulation = run_streamlit_simulation(prices_df, rates_df, scenario)

if simulation.empty:
    st.warning("시뮬레이션에 필요한 TQQQ, QLD, SPYM, BOXX 데이터가 충분하지 않습니다.")
    st.stop()

last = simulation.iloc[-1]

col1, col2, col3, col4 = st.columns(4)
col1.metric("최신 거래일", latest or "-")
col2.metric("부부 합산 총자산", won(last["couple_total"]))
col3.metric("본인 총자산", won(last["self_total"]))
col4.metric("아내 총자산", won(last["spouse_total"]))

col5, col6, col7 = st.columns(3)
col5.metric("본인 누적 인출", won(last["self_withdrawal"]))
col6.metric("아내 누적 인출", won(last["spouse_withdrawal"]))
col7.metric("월 인출일", f"매월 {MONTHLY_WITHDRAWAL_DAY}일")

st.subheader("총자산 추이")
asset_chart = simulation[["date", "couple_total", "self_total", "spouse_total"]].melt(
    id_vars="date",
    var_name="구분",
    value_name="금액",
)
st.plotly_chart(px.line(asset_chart, x="date", y="금액", color="구분"), use_container_width=True)

st.subheader("TQQQ 종가와 200일선")
tqqq_chart = simulation[["date", "tqqq_close", "tqqq_ma200"]].melt(
    id_vars="date",
    var_name="구분",
    value_name="가격",
)
st.plotly_chart(px.line(tqqq_chart, x="date", y="가격", color="구분"), use_container_width=True)

st.subheader("저장된 최신 종가")
latest_prices = (
    prices_df.sort_values("trade_date")
    .groupby("symbol", as_index=False)
    .tail(1)
    .sort_values("symbol")
)
st.dataframe(latest_prices, use_container_width=True, hide_index=True)

with st.expander("운영 메모"):
    st.markdown(
        """
        - 매일 종가 수집은 GitHub Actions가 `scripts/collect_market_data.py`를 실행하는 방식입니다.
        - 현재 Streamlit 버전의 시뮬레이션은 실제 데이터 연결을 빠르게 확인하기 위한 운영용 초안입니다.
        - 3일 분할매수와 거래내역 전체 저장은 TypeScript 엔진에 더 정확히 구현되어 있어, 다음 단계에서 Python 엔진에도 동일하게 확장해야 합니다.
        """
    )

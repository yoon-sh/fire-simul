from __future__ import annotations

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
    page_icon="FIRE",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background: #101827;
        color: #f3f7fb;
    }
    [data-testid="stSidebar"] {
        background: #182235;
        border-right: 1px solid #334155;
    }
    [data-testid="stMetric"] {
        background: #182235;
        border: 1px solid #3b4a60;
        border-radius: 10px;
        padding: 16px;
    }
    [data-testid="stMetricLabel"] {
        color: #c7d2e0;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff;
    }
    h1, h2, h3 {
        color: #ffffff;
    }
    p, span, label, div {
        color: inherit;
    }
    [data-testid="stMarkdownContainer"] {
        color: #eef4fb;
    }
    [data-baseweb="select"] div {
        color: #0f172a;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid #3b4a60;
        border-radius: 10px;
    }
    .data-note {
        background: #182235;
        border: 1px solid #3b4a60;
        border-radius: 10px;
        padding: 12px 14px;
        color: #dbeafe;
        line-height: 1.5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PLOT_TEMPLATE = "plotly_dark"
PLOT_BG = "#182235"
PAGE_BG = "#101827"
TEXT_COLOR = "#f8fafc"
MUTED_TEXT_COLOR = "#dbeafe"


def won(value: float | int) -> str:
    return f"{round(value):,}원"


def style_chart(fig):
    fig.update_layout(
        paper_bgcolor=PAGE_BG,
        plot_bgcolor=PLOT_BG,
        font_color=TEXT_COLOR,
        legend=dict(
            font=dict(color=TEXT_COLOR, size=13),
            title=dict(font=dict(color=TEXT_COLOR, size=13)),
            bgcolor="rgba(24, 34, 53, 0.88)",
            bordercolor="#475569",
            borderwidth=1,
        ),
        xaxis=dict(
            title_font=dict(color=TEXT_COLOR),
            tickfont=dict(color=MUTED_TEXT_COLOR),
            gridcolor="#334155",
            zerolinecolor="#475569",
        ),
        yaxis=dict(
            title_font=dict(color=TEXT_COLOR),
            tickfont=dict(color=MUTED_TEXT_COLOR),
            gridcolor="#334155",
            zerolinecolor="#475569",
        ),
        hoverlabel=dict(
            bgcolor="#0f172a",
            bordercolor="#64748b",
            font=dict(color=TEXT_COLOR),
        ),
    )
    return fig


@st.cache_data(ttl=600)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    client = get_client(service_role=False)
    prices = load_market_prices(client, START_DATE)
    rates = load_exchange_rates(client, START_DATE)
    return prices, rates


st.title("FIRE 자산운용 시뮬레이터")
st.caption("합산 자산 기준으로 실제 종가 데이터를 반영해 FIRE 가능성을 매일 갱신합니다.")

with st.sidebar:
    st.header("설정")
    scenario = st.selectbox(
        "부부 합산 초기자산",
        options=[900_000_000, 1_200_000_000, 1_500_000_000],
        format_func=lambda value: f"{value // 100_000_000}억 원",
        index=1,
    )
    st.info(f"생활비 인출일은 매월 {MONTHLY_WITHDRAWAL_DAY}일, 합산 월 인출액은 600만 원입니다.")
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

required_symbols = ["TQQQ", "QLD", "SPYM", "BOXX"]
coverage = (
    prices_df[prices_df["symbol"].isin(required_symbols)]
    .groupby("symbol")
    .agg(데이터수=("trade_date", "nunique"), 시작일=("trade_date", "min"), 마지막일=("trade_date", "max"))
    .reindex(required_symbols)
    .reset_index()
    .rename(columns={"symbol": "종목"})
)

if simulation.empty:
    st.warning("시뮬레이션에 필요한 종목 데이터가 아직 부족합니다. 아래 표에서 비어 있는 종목을 확인하세요.")
    st.dataframe(coverage, use_container_width=True, hide_index=True)
    st.stop()

last = simulation.iloc[-1]

if last["tqqq_ma_count"] < 200:
    st.markdown(
        f"""
        <div class="data-note">
        현재 TQQQ 200일선은 저장된 TQQQ 데이터 {int(last["tqqq_ma_count"])}개로 계산한 임시값입니다.
        GitHub Actions에서 2025-06-01부터 데이터를 다시 수집하면 200거래일 기준에 가까워집니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

col1, col2, col3, col4 = st.columns(4)
col1.metric("최신 거래일", latest or "-")
col2.metric("부부 합산 총자산", won(last["couple_total"]))
col3.metric("성장자산", won(last["growth_assets"]))
col4.metric("방어자산", won(last["defense_assets"]))

col5, col6, col7 = st.columns(3)
col5.metric("누적 생활비 인출", won(last["couple_withdrawal"]))
col6.metric("TQQQ 종가", f"{last['tqqq_close']:,.2f}")
col7.metric("TQQQ 200일선", f"{last['tqqq_ma200']:,.2f}")

st.subheader("합산 총자산 추이")
asset_chart = simulation[["date", "couple_total"]].melt(
    id_vars="date",
    var_name="구분",
    value_name="금액",
)
fig_total = px.line(asset_chart, x="date", y="금액", color="구분", template=PLOT_TEMPLATE)
fig_total = style_chart(fig_total)
st.plotly_chart(fig_total, use_container_width=True)

st.subheader("종목별 자산 변화")
asset_by_symbol = simulation[
    ["date", "tqqq_value", "qld_value", "qld_cash_value", "spym_value", "boxx_value"]
].melt(id_vars="date", var_name="자산", value_name="금액")
name_map = {
    "tqqq_value": "TQQQ",
    "qld_value": "QLD",
    "qld_cash_value": "QLD 대기현금",
    "spym_value": "SPYM",
    "boxx_value": "BOXX",
}
asset_by_symbol["자산"] = asset_by_symbol["자산"].map(name_map)
fig_symbols = px.area(asset_by_symbol, x="date", y="금액", color="자산", template=PLOT_TEMPLATE)
fig_symbols = style_chart(fig_symbols)
st.plotly_chart(fig_symbols, use_container_width=True)

st.subheader("자산군별 변화")
asset_group = simulation[["date", "growth_assets", "defense_assets", "qld_cash_value"]].melt(
    id_vars="date",
    var_name="자산군",
    value_name="금액",
)
group_map = {
    "growth_assets": "성장자산(TQQQ+QLD)",
    "defense_assets": "방어자산(SPYM+BOXX)",
    "qld_cash_value": "QLD 대기현금",
}
asset_group["자산군"] = asset_group["자산군"].map(group_map)
fig_groups = px.line(asset_group, x="date", y="금액", color="자산군", template=PLOT_TEMPLATE)
fig_groups = style_chart(fig_groups)
st.plotly_chart(fig_groups, use_container_width=True)

st.subheader("TQQQ 종가와 200일선")
tqqq_chart = simulation[["date", "tqqq_close", "tqqq_ma200"]].melt(
    id_vars="date",
    var_name="구분",
    value_name="가격",
)
fig_tqqq = px.line(tqqq_chart, x="date", y="가격", color="구분", template=PLOT_TEMPLATE)
fig_tqqq = style_chart(fig_tqqq)
st.plotly_chart(fig_tqqq, use_container_width=True)

st.subheader("데이터 보유 현황")
st.dataframe(coverage, use_container_width=True, hide_index=True)

st.subheader("저장된 최신 종가")
latest_prices = (
    prices_df.assign(
        close=pd.to_numeric(prices_df["close"], errors="coerce"),
        source_priority=prices_df["source"].map({"yfinance": 0, "stooq": 1}).fillna(9),
    )
    .sort_values(["trade_date", "symbol", "source_priority"])
    .drop_duplicates(["trade_date", "symbol"], keep="first")
    .groupby("symbol", as_index=False)
    .tail(1)
    .sort_values("symbol")
)
latest_prices = latest_prices.drop(columns=["source_priority"])
st.dataframe(latest_prices, use_container_width=True, hide_index=True)

with st.expander("운영 메모"):
    st.markdown(
        """
        - 매일 종가 수집은 GitHub Actions가 `scripts/collect_market_data.py`를 실행하는 방식입니다.
        - 화면은 본인/아내를 나누지 않고 부부 합산 자산만 표시합니다.
        - TQQQ 200일선은 저장된 TQQQ 종가로 직접 계산합니다. 데이터 제공처에서 200일선을 별도 지표로 받는 방식은 아직 사용하지 않습니다.
        - 3일 분할매수와 거래내역 전체 저장은 다음 단계에서 Python 엔진에 더 정밀하게 확장해야 합니다.
        """
    )

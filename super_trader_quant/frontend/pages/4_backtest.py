from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.data_providers.factory import get_provider
from super_trader_quant.backend.app.engine.backtester import run_backtest
from super_trader_quant.backend.app.strategies import STRATEGY_REGISTRY

st.title("Backtest rápido")
symbol = st.text_input("Ativo", "PETR4.SA")
provider_options = ["simulated", "yfinance", "brapi", "stooq"]
provider_name = st.selectbox(
    "Provider",
    provider_options,
    index=provider_options.index(settings.default_provider if settings.default_provider in provider_options else "simulated"),
)
timeframe = st.selectbox("Timeframe", ["H1", "D1", "W1"], index=1)
period = st.text_input("Período", "1y")
strategy_name = st.selectbox("Setup", list(STRATEGY_REGISTRY.keys()))
if st.button("Rodar backtest"):
    provider = get_provider(provider_name)
    df = provider.fetch_history(symbol, timeframe=timeframe, period=period)
    trades, metrics = run_backtest(df, STRATEGY_REGISTRY[strategy_name]())
    st.json(metrics)
    st.dataframe(trades, use_container_width=True)

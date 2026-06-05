from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from sqlalchemy import desc
from sqlmodel import Session, select
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.models.asset import Asset
from super_trader_quant.backend.app.models.memory import SetupMemory
from super_trader_quant.backend.app.models.signal import Signal

st.set_page_config(page_title="SUPER_TRADER_QUANT", layout="wide")
init_db()

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(0, 255, 170, 0.10), transparent 28%),
            radial-gradient(circle at top right, rgba(0, 140, 255, 0.08), transparent 24%),
            #0b1020;
    }
    h1, h2, h3 {
        letter-spacing: 0.02em;
    }
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 18px;
        padding: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("SUPER_TRADER_QUANT")
st.caption("SIMULAÇÃO — NÃO É CONTA REAL | Rentabilidade passada não garante resultado futuro")

with Session(engine) as session:
    assets = session.exec(select(Asset)).all()
    signals = session.exec(select(Signal).order_by(desc(Signal.signal_time))).all()
    open_signals = [signal for signal in signals if signal.status == "open"]
    memories = session.exec(select(SetupMemory)).all()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ativos demo", len(assets))
c2.metric("Sinais totais", len(signals))
c3.metric("Sinais abertos", len(open_signals))
c4.metric("Memórias históricas", len(memories))

st.subheader("Últimos sinais")
if signals:
    st.dataframe([
        {
            "ativo": s.asset_symbol,
            "setup": s.strategy,
            "status": s.status,
            "entrada": round(s.entry, 2),
            "stop": round(s.stop, 2),
            "alvo": round(s.target, 2),
            "resultado_%": None if s.pnl_pct is None else round(s.pnl_pct, 2),
        }
        for s in signals[:20]
    ], use_container_width=True)
else:
    st.info("Nenhum sinal registrado ainda.")

st.subheader("Memória histórica por ativo/setup")
if memories:
    st.dataframe([
        {
            "ativo": m.asset_symbol,
            "setup": m.strategy,
            "timeframe": m.timeframe,
            "sinais": m.total_signals,
            "acertos": m.successes,
            "falhas": m.failures,
            "expirados": m.expired,
            "win_rate_%": round(m.win_rate * 100, 2),
            "pnl_médio_%": round(m.avg_pnl_pct, 2),
        }
        for m in memories
    ], use_container_width=True)
else:
    st.info("A memória aparecerá após os primeiros sinais serem resolvidos.")

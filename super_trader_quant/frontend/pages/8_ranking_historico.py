from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from sqlmodel import Session, select
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.models.memory import SetupMemory

st.title("Ranking histórico")
init_db()
with Session(engine) as session:
    memories = session.exec(select(SetupMemory)).all()
rows = [m.model_dump() for m in memories]
rows = sorted(rows, key=lambda item: (item["win_rate"], item["avg_pnl_pct"]), reverse=True)
st.dataframe(rows, use_container_width=True)

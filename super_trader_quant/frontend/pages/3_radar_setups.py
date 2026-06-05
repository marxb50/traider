from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from sqlmodel import Session, select
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.models.signal import Signal

st.title("Radar de setups")
init_db()
with Session(engine) as session:
    open_signals = session.exec(select(Signal).where(Signal.status == "open")).all()
st.dataframe([signal.model_dump() for signal in open_signals], use_container_width=True)

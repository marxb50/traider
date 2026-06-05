from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from sqlmodel import Session, select
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.models.asset import Asset

st.title("Ativos demo")
init_db()
with Session(engine) as session:
    assets = session.exec(select(Asset)).all()
st.dataframe([asset.model_dump() for asset in assets], use_container_width=True)

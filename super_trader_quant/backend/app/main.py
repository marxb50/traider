from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import init_db
from .api.routes_assets import router as assets_router
from .api.routes_signals import router as signals_router
from .api.routes_memory import router as memory_router
from .api.routes_ops import router as ops_router

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="SUPER_TRADER_QUANT", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(assets_router)
app.include_router(signals_router)
app.include_router(memory_router)
app.include_router(ops_router)

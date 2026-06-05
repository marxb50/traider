from .base import BaseProvider
from .brapi_provider import BrapiProvider
from .simulated_provider import SimulatedProvider
from .stooq_provider import StooqProvider
from .yfinance_provider import YFinanceProvider


def get_provider(name: str) -> BaseProvider:
    providers = {
        "brapi": BrapiProvider,
        "simulated": SimulatedProvider,
        "stooq": StooqProvider,
        "yfinance": YFinanceProvider,
    }
    try:
        return providers[name.lower()]()
    except KeyError as exc:
        raise ValueError(f"Provider desconhecido: {name}") from exc

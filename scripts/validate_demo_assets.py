from super_trader_quant.backend.app.data_providers.yfinance_provider import YFinanceProvider
from super_trader_quant.backend.app.demo_assets import DEMO_ASSETS_BY_MARKET


def main() -> None:
    provider = YFinanceProvider()
    missing_by_market: dict[str, list[str]] = {}
    for market, symbols in DEMO_ASSETS_BY_MARKET.items():
        frames = provider.fetch_many_history(symbols, period="1y")
        missing_by_market[market] = [
            symbol for symbol, frame in frames.items() if frame.empty
        ]
        print(f"{market}: {len(symbols) - len(missing_by_market[market])}/{len(symbols)} disponíveis")
        if missing_by_market[market]:
            print(f"  sem dados: {', '.join(missing_by_market[market])}")

    if any(missing_by_market.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

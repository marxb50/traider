import argparse
import json
from pathlib import Path

from super_trader_quant.backend.app.data_providers.factory import get_provider
from super_trader_quant.backend.app.demo_assets import DEMO_ASSETS_BY_MARKET
from super_trader_quant.backend.app.engine.backtester import run_backtest
from super_trader_quant.backend.app.strategies import STRATEGY_REGISTRY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="simulated")
    parser.add_argument("--market", default="BR")
    parser.add_argument("--timeframe", default="D1")
    parser.add_argument("--period", default="1y")
    parser.add_argument("--limit", type=int, help="Limita a quantidade de ativos processados.")
    parser.add_argument("--output", help="Salva o batch completo em JSON.")
    args = parser.parse_args()
    provider = get_provider(args.provider)
    symbols = list(DEMO_ASSETS_BY_MARKET[args.market.upper()])
    if args.limit:
        symbols = symbols[: args.limit]
    report: list[dict[str, object]] = []
    for symbol in symbols:
        try:
            df = provider.fetch_history(symbol, timeframe=args.timeframe, period=args.period)
        except Exception as exc:
            report.append(
                {
                    "symbol": symbol,
                    "provider": args.provider,
                    "timeframe": args.timeframe,
                    "period": args.period,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue
        for strategy_cls in STRATEGY_REGISTRY.values():
            try:
                _, metrics = run_backtest(df, strategy_cls())
                row = {
                    "symbol": symbol,
                    "strategy": strategy_cls.name,
                    "provider": args.provider,
                    "timeframe": args.timeframe,
                    "period": args.period,
                    "ok": True,
                    **metrics,
                }
                report.append(row)
                print(symbol, strategy_cls.name, metrics)
            except Exception as exc:
                report.append(
                    {
                        "symbol": symbol,
                        "strategy": strategy_cls.name,
                        "provider": args.provider,
                        "timeframe": args.timeframe,
                        "period": args.period,
                        "ok": False,
                        "error": str(exc),
                    }
                )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

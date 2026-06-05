import argparse

from super_trader_quant.backend.app.services.telegram_service import (
    PRIMARY_ROUTE,
    get_telegram_route_chat_ids,
    get_telegram_route_token,
    send_telegram_message,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Envia um teste Telegram para uma rota configurada.")
    parser.add_argument("--route", default=PRIMARY_ROUTE, help="Rota Telegram: primary ou br.")
    args = parser.parse_args()

    if not get_telegram_route_token(args.route):
        raise SystemExit(f"Token Telegram nao configurado para a rota {args.route}")
    if not get_telegram_route_chat_ids(args.route):
        raise SystemExit(f"Destinatarios Telegram nao configurados para a rota {args.route}")
    delivered_to = send_telegram_message(
        "[SUPER_TRADER_QUANT] Teste de alerta Telegram - SIMULACAO",
        route=args.route,
    )
    print(f"Mensagem enviada para ({args.route}): {', '.join(delivered_to)}")


if __name__ == "__main__":
    main()

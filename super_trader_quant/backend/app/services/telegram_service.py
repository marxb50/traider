import logging

import requests

from ..config import settings

logger = logging.getLogger(__name__)

PRIMARY_ROUTE = "primary"
BRAZIL_ROUTE = "br"


def _validated_route(route: str) -> str:
    if route not in {PRIMARY_ROUTE, BRAZIL_ROUTE}:
        raise ValueError(f"Rota Telegram desconhecida: {route}")
    return route


def get_telegram_route_chat_ids(route: str = PRIMARY_ROUTE) -> list[str]:
    route = _validated_route(route)
    if route == BRAZIL_ROUTE:
        return settings.telegram_br_chat_id_list
    return settings.telegram_chat_id_list


def get_telegram_route_token(route: str = PRIMARY_ROUTE) -> str:
    route = _validated_route(route)
    if route == BRAZIL_ROUTE:
        return settings.telegram_br_bot_token.strip()
    return settings.telegram_bot_token.strip()


def is_telegram_route_partially_configured(route: str = PRIMARY_ROUTE) -> bool:
    return bool(get_telegram_route_token(route) or get_telegram_route_chat_ids(route))


def send_telegram_message(
    message: str,
    chat_ids: list[str] | None = None,
    *,
    route: str = PRIMARY_ROUTE,
) -> list[str]:
    route = _validated_route(route)
    bot_token = get_telegram_route_token(route)
    if not bot_token:
        logger.info("Telegram route %s não configurada; alerta apenas registrado em log: %s", route, message)
        return []
    recipients = chat_ids if chat_ids is not None else get_telegram_route_chat_ids(route)
    delivered_to: list[str] = []
    for chat_id in recipients:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=20)
        response.raise_for_status()
        delivered_to.append(chat_id)
    return delivered_to

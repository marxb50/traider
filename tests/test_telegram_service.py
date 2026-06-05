from super_trader_quant.backend.app.services import telegram_service


class FakeResponse:
    def raise_for_status(self):
        return None


def test_telegram_sends_to_all_configured_chat_ids(monkeypatch):
    sent_payloads = []

    def fake_post(url, json, timeout):
        sent_payloads.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(telegram_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(telegram_service.settings, "telegram_chat_ids", "111111111,123456789")
    monkeypatch.setattr(telegram_service.requests, "post", fake_post)

    delivered_to = telegram_service.send_telegram_message("alerta de teste")

    assert delivered_to == ["111111111", "123456789"]
    assert [item[1]["chat_id"] for item in sent_payloads] == ["111111111", "123456789"]
    assert all(item[1]["text"] == "alerta de teste" for item in sent_payloads)


def test_telegram_can_target_one_chat_id(monkeypatch):
    sent_payloads = []

    def fake_post(url, json, timeout):
        sent_payloads.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(telegram_service.settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(telegram_service.settings, "telegram_chat_ids", "111111111,123456789")
    monkeypatch.setattr(telegram_service.requests, "post", fake_post)

    delivered_to = telegram_service.send_telegram_message("alerta de teste", chat_ids=["123456789"])

    assert delivered_to == ["123456789"]
    assert [item[1]["chat_id"] for item in sent_payloads] == ["123456789"]


def test_telegram_br_route_uses_dedicated_token_and_recipients(monkeypatch):
    sent_payloads = []

    def fake_post(url, json, timeout):
        sent_payloads.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(telegram_service.settings, "telegram_br_bot_token", "br-token-456")
    monkeypatch.setattr(telegram_service.settings, "telegram_br_chat_ids", "555,777")
    monkeypatch.setattr(telegram_service.requests, "post", fake_post)

    delivered_to = telegram_service.send_telegram_message(
        "alerta br",
        route=telegram_service.BRAZIL_ROUTE,
    )

    assert delivered_to == ["555", "777"]
    assert all("br-token-456" in item[0] for item in sent_payloads)
    assert [item[1]["chat_id"] for item in sent_payloads] == ["555", "777"]

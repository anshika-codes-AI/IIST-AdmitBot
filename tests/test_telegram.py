"""Tests for Telegram webhook payload parsing."""

from backend.integrations.telegram import TelegramMessage, parse_webhook_update


def _telegram_payload(text: str = "hello") -> dict:
    return {
        "update_id": 10000,
        "message": {
            "message_id": 1365,
            "from": {
                "id": 123456789,
                "is_bot": False,
                "first_name": "Rahul",
                "last_name": "Sharma",
                "username": "rahul_test",
                "language_code": "en",
            },
            "chat": {
                "id": 123456789,
                "first_name": "Rahul",
                "username": "rahul_test",
                "type": "private",
            },
            "date": 1710000000,
            "text": text,
        },
    }


class TestParseTelegramUpdate:
    def test_parses_valid_text_message(self):
        msgs = parse_webhook_update(_telegram_payload("CSE fees?"))
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg.chat_id == "123456789"
        assert msg.user_id == "123456789"
        assert msg.message_text == "CSE fees?"
        assert msg.name == "Rahul Sharma"
        assert msg.username == "rahul_test"

    def test_empty_payload_returns_empty_list(self):
        assert parse_webhook_update({}) == []

    def test_non_text_message_returns_empty(self):
        payload = _telegram_payload()
        payload["message"].pop("text")
        assert parse_webhook_update(payload) == []


class TestTelegramMessageRepr:
    def test_repr_contains_chat_and_text(self):
        msg = TelegramMessage(
            chat_id="999",
            message_text="Hello from telegram",
            message_id="1",
            user_id="99",
            name="Rahul",
        )
        r = repr(msg)
        assert "999" in r
        assert "Hello" in r

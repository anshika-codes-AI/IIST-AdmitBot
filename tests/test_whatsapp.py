"""Tests for WhatsApp webhook payload parsing."""

import pytest

from backend.integrations.whatsapp import WhatsAppMessage, parse_webhook_payload


def _make_payload(
    wa_id: str = "919876543210",
    name: str = "Rahul Sharma",
    text: str = "Hello",
    msg_type: str = "text",
) -> dict:
    """Build a minimal valid Meta webhook payload."""
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": "wamid.abc123",
                                    "type": msg_type,
                                    "text": {"body": text},
                                    "timestamp": "1700000000",
                                }
                            ],
                            "contacts": [
                                {
                                    "wa_id": wa_id,
                                    "profile": {"name": name},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


class TestParseWebhookPayload:
    def test_parses_valid_payload(self):
        msgs = parse_webhook_payload(_make_payload())
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg.phone_number == "+919876543210"
        assert msg.message_text == "Hello"
        assert msg.name == "Rahul Sharma"
        assert msg.wa_id == "919876543210"

    def test_phone_number_prefixed_with_plus(self):
        msgs = parse_webhook_payload(_make_payload(wa_id="919999999999"))
        assert msgs[0].phone_number.startswith("+")

    def test_empty_payload_returns_empty_list(self):
        assert parse_webhook_payload({}) == []

    def test_empty_entry_list(self):
        assert parse_webhook_payload({"entry": []}) == []

    def test_non_text_message_skipped(self):
        payload = _make_payload(msg_type="image")
        assert parse_webhook_payload(payload) == []

    def test_malformed_payload_returns_empty_list(self):
        assert parse_webhook_payload({"entry": "not_a_list"}) == []

    def test_missing_text_body(self):
        payload = _make_payload()
        # Remove text body
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"] = {}
        msgs = parse_webhook_payload(payload)
        assert len(msgs) == 1
        assert msgs[0].message_text == ""

    def test_multiple_messages_in_one_payload(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "919111111111",
                                        "id": "id1",
                                        "type": "text",
                                        "text": {"body": "msg1"},
                                        "timestamp": "1700000001",
                                    },
                                    {
                                        "from": "919222222222",
                                        "id": "id2",
                                        "type": "text",
                                        "text": {"body": "msg2"},
                                        "timestamp": "1700000002",
                                    },
                                ],
                                "contacts": [],
                            }
                        }
                    ]
                }
            ]
        }
        msgs = parse_webhook_payload(payload)
        assert len(msgs) == 2
        assert msgs[0].message_text == "msg1"
        assert msgs[1].message_text == "msg2"


class TestWhatsAppMessageRepr:
    def test_repr_shows_phone_and_truncated_text(self):
        msg = WhatsAppMessage(
            phone_number="+919876543210",
            message_text="Hello, I want to know about CSE admission",
            message_id="id1",
            wa_id="919876543210",
            name="Rahul",
        )
        r = repr(msg)
        assert "+919876543210" in r
        assert "Hello" in r

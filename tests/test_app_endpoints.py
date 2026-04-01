"""FastAPI endpoint tests for health, webhooks, and /api/chat."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app import app
from backend import config
from backend.chatbot.ai_client import AIResponse


client = TestClient(app)


def _admin_login(username: str = "admin", password: str = "admin123"):
    return client.post(
        "/api/admin/auth/login",
        json={"username": username, "password": password},
    )


def _sample_whatsapp_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.1",
                                    "type": "text",
                                    "text": {"body": "What are CSE fees?"},
                                    "timestamp": "1700000000",
                                }
                            ],
                            "contacts": [
                                {
                                    "wa_id": "919876543210",
                                    "profile": {"name": "Rahul"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _sample_telegram_payload(text: str = "What are CSE fees?") -> dict:
    return {
        "update_id": 10000,
        "message": {
            "message_id": 1365,
            "from": {
                "id": 123456789,
                "is_bot": False,
                "first_name": "Rahul",
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


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestWhatsAppVerifyEndpoint:
    def test_verify_fails_with_wrong_token(self):
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "abc123",
            },
        )
        assert resp.status_code == 403

    def test_verify_fails_with_wrong_mode(self):
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "wrong",
                "hub.verify_token": "iist_admitbot_verify",
                "hub.challenge": "abc123",
            },
        )
        assert resp.status_code == 403

    def test_verify_succeeds_with_correct_token(self):
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "iist_admitbot_verify",
                "hub.challenge": "abc123",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "abc123"


class TestWhatsAppWebhookEndpoint:
    def test_webhook_accepts_valid_payload(self):
        resp = client.post("/webhook/whatsapp", json=_sample_whatsapp_payload())
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_webhook_accepts_empty_payload(self):
        resp = client.post("/webhook/whatsapp", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTawktoWebhookEndpoint:
    def test_tawkto_ignores_non_chat_events(self):
        resp = client.post("/webhook/tawkto", json={"event": "visitor:join"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"

    def test_tawkto_empty_message(self):
        payload = {
            "event": "chat:message",
            "visitor": {"name": "Web User", "phone": "+919999999999"},
            "message": {"text": ""},
        }
        resp = client.post("/webhook/tawkto", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTelegramWebhookEndpoint:
    def test_telegram_webhook_rejects_wrong_secret(self):
        resp = client.post("/webhook/telegram/wrong_secret", json=_sample_telegram_payload())
        assert resp.status_code == 403

    def test_telegram_webhook_accepts_correct_secret(self):
        with patch.object(config.settings, "telegram_webhook_secret", "ok_secret"):
            # No token configured in tests, send_telegram_message logs and returns False,
            # but webhook handler should still process safely.
            resp = client.post("/webhook/telegram/ok_secret", json=_sample_telegram_payload())
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_tawkto_message_processed(self):
        payload = {
            "event": "chat:message",
            "visitor": {"name": "Web User", "phone": "+919999999999"},
            "message": {"text": "Tell me about hostel fees"},
        }
        resp = client.post("/webhook/tawkto", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestApiChatEndpoint:
    def test_api_chat_returns_reply(self):
        resp = client.post(
            "/api/chat",
            json={"message": "What are CSE fees?", "session_id": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert data["session_id"]
        assert data["lead_score"] in {"Hot", "Warm", "Cold"}
        assert data["language"] in {"hindi", "hinglish", "english"}

    def test_api_chat_preserves_session_id(self):
        first = client.post("/api/chat", json={"message": "hello"})
        sid = first.json()["session_id"]

        second = client.post(
            "/api/chat",
            json={"message": "fees?", "session_id": sid},
        )
        assert second.status_code == 200
        assert second.json()["session_id"] == sid

    def test_api_chat_with_name_and_phone(self):
        resp = client.post(
            "/api/chat",
            json={
                "message": "I want admission",
                "name": "Rahul",
                "phone": "+919123456789",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"]

    def test_api_chat_avoids_repeated_handoff_loop_after_ack(self):
        with patch("backend.app.generate_response", new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = [
                AIResponse(
                    reply_text="I will connect you with our admissions team. They will call you soon.",
                    intent_score="Warm",
                    extracted_data={},
                    needs_escalation=True,
                ),
                AIResponse(
                    reply_text="I will connect you with our admissions team. They will call you soon.",
                    intent_score="Warm",
                    extracted_data={},
                    needs_escalation=True,
                ),
            ]

            first = client.post(
                "/api/chat",
                json={"message": "9575383029", "session_id": "s-escalation"},
            )
            assert first.status_code == 200

            second = client.post(
                "/api/chat",
                json={"message": "okay", "session_id": "s-escalation"},
            )
            assert second.status_code == 200
            data = second.json()
            assert data["needs_escalation"] is False
            assert "details are shared" in data["reply"].lower()

    def test_api_chat_suppresses_unnecessary_escalation_for_faq_query(self):
        with patch("backend.app.generate_response", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = AIResponse(
                reply_text="Our admissions team will contact you shortly.",
                intent_score="Warm",
                extracted_data={},
                needs_escalation=True,
            )

            resp = client.post(
                "/api/chat",
                json={"message": "what are cse fees?", "session_id": "s-faq-no-handoff"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["needs_escalation"] is False
            assert "₹" in data["reply"] or "fee" in data["reply"].lower()


class TestApiLeadsEndpoint:
    def test_api_leads_requires_auth_without_session_or_token(self):
        with patch.object(config.settings, "api_secret_key", ""):
            resp = client.get("/api/leads")
        assert resp.status_code == 401

    def test_api_leads_rejects_wrong_token(self):
        with patch.object(config.settings, "api_secret_key", "real_secret"):
            resp = client.get("/api/leads", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_api_leads_accepts_correct_token(self):
        with patch.object(config.settings, "api_secret_key", "real_secret"):
            resp = client.get("/api/leads", headers={"Authorization": "Bearer real_secret"})
        assert resp.status_code == 200

    def test_api_leads_accepts_admin_session(self):
        with patch.object(config.settings, "api_secret_key", ""):
            login = _admin_login()
            assert login.status_code == 200
            resp = client.get("/api/leads")
        assert resp.status_code == 200


class TestAdminDashboardEndpoints:
    def test_admin_page_serves_html(self):
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_admin_login_and_me(self):
        login = _admin_login()
        assert login.status_code == 200
        resp = client.get("/api/admin/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["user"]["role"] in {"admin", "viewer"}

    def test_admin_overview_rejects_without_auth(self):
        with patch.object(config.settings, "api_secret_key", ""):
            client.post("/api/admin/auth/logout")
            resp = client.get("/api/admin/overview")
        assert resp.status_code == 401

    def test_admin_overview_exposes_groq_mode_after_login(self):
        login = _admin_login()
        assert login.status_code == 200
        resp = client.get("/api/admin/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ai_provider"]["mode"] == "groq-only"
        assert data["ai_provider"]["provider"] == "groq"
        assert "analytics" in data
        assert "source_roi" in data["analytics"]
        assert "regional_heat" in data["analytics"]
        assert "recent_enquiries" in data["analytics"]
        assert "persistent_totals" in data["analytics"]

    def test_admin_logout_clears_session(self):
        login = _admin_login()
        assert login.status_code == 200
        logout = client.post("/api/admin/auth/logout")
        assert logout.status_code == 200
        me = client.get("/api/admin/auth/me")
        assert me.status_code == 401

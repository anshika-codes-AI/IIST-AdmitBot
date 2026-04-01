"""
IIST AdmitBot — Application Configuration
All settings loaded from environment variables (via .env file or Railway env vars).
"""

import json
import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # AI Provider — Groq-only mode ("auto" kept as alias to Groq for compatibility)
    ai_provider: str = "groq"

    # Groq (free tier — get key at console.groq.com)
    groq_api_key: str = ""

    # Legacy keys are retained for backward compatibility with older env files.
    openai_api_key: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # Meta WhatsApp Business API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "iist_admitbot_verify"
    whatsapp_api_version: str = "v19.0"

    # Telegram Bot API
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = "iist_telegram_secret"

    # Google Sheets
    google_service_account_file: str = "service_account.json"
    google_service_account_json: str = ""
    google_sheets_id: str = ""
    google_sheets_leads_tab: str = "Leads"
    google_sheets_interactions_tab: str = "Interactions"

    # Counsellor round-robin
    counsellor_numbers: str = ""

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_allowed_origins: str = "*"

    # Simple API key to protect /api/leads and other internal endpoints
    api_secret_key: str = ""

    # Admin auth and roles
    admin_session_secret: str = "change-me-admin-session-secret"
    admin_users_json: str = (
        '[{"username":"admin","password":"admin123","role":"admin"},'
        '{"username":"viewer","password":"viewer123","role":"viewer"}]'
    )

    # n8n
    n8n_webhook_url: str = ""
    n8n_api_url: str = ""
    n8n_api_key: str = ""

    # Tawk.to
    tawkto_api_key: str = ""

    # Reporting / dashboard recipients
    hod_whatsapp_number: str = ""
    principal_whatsapp_number: str = ""
    looker_dashboard_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @property
    def counsellor_list(self) -> List[str]:
        """Return counsellor numbers as a list."""
        if not self.counsellor_numbers:
            return []
        return [n.strip() for n in self.counsellor_numbers.split(",") if n.strip()]

    @property
    def cors_allowed_origins_list(self) -> List[str]:
        """Return configured CORS origins, supporting '*' or comma-separated values."""
        if not self.cors_allowed_origins:
            return ["*"]
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def whatsapp_api_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.whatsapp_api_version}"
            f"/{self.whatsapp_phone_number_id}/messages"
        )

    @property
    def admin_users(self) -> List[dict]:
        """Return admin users from JSON env with safe fallback."""
        if not self.admin_users_json:
            return []
        try:
            raw = json.loads(self.admin_users_json)
            if isinstance(raw, list):
                users = []
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    username = str(item.get("username", "")).strip()
                    password = str(item.get("password", ""))
                    role = str(item.get("role", "viewer")).strip().lower()
                    if username and password:
                        users.append(
                            {
                                "username": username,
                                "password": password,
                                "role": role if role in {"admin", "viewer"} else "viewer",
                            }
                        )
                return users
        except Exception:
            return []
        return []


settings = Settings()

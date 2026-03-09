"""
IIST AdmitBot — Application Configuration
All settings loaded from environment variables (via .env file or Railway env vars).
"""

import json
import os
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gemini AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # Meta WhatsApp Business API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "iist_admitbot_verify"
    whatsapp_api_version: str = "v19.0"

    # Google Sheets
    google_service_account_file: str = "service_account.json"
    google_service_account_json: str = ""
    google_sheets_id: str = ""
    google_sheets_leads_tab: str = "Leads"

    # Counsellor round-robin
    counsellor_numbers: str = ""

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # n8n
    n8n_webhook_url: str = ""

    # Tawk.to
    tawkto_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def counsellor_list(self) -> List[str]:
        """Return counsellor numbers as a list."""
        if not self.counsellor_numbers:
            return []
        return [n.strip() for n in self.counsellor_numbers.split(",") if n.strip()]

    @property
    def whatsapp_api_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.whatsapp_api_version}"
            f"/{self.whatsapp_phone_number_id}/messages"
        )


settings = Settings()

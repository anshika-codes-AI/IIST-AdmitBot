"""Validate consistency between knowledge_base_document.txt and knowledge_base_structured.json.

Usage:
  a:/IIST-AdmissionChatBot/.venv/Scripts/python.exe scripts/validate_knowledge_base.py

Exit code:
  0 = pass
  1 = validation failed
"""

from __future__ import annotations

import json
from pathlib import Path


def _contains(document: str, value: str) -> bool:
    return value.lower() in document.lower()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    doc_path = root / "backend" / "chatbot" / "knowledge_base_document.txt"
    json_path = root / "backend" / "chatbot" / "knowledge_base_structured.json"

    document = doc_path.read_text(encoding="utf-8")
    data = json.loads(json_path.read_text(encoding="utf-8"))

    failures: list[str] = []

    website = data["official_identity"]["website"]
    admissions_portal = data["official_identity"]["admissions_portal"]
    email = data["official_identity"]["email"]
    phones = data["official_identity"]["phones"]
    document_link = data["documents"]["official_pdf"]

    required_programs = data["programs"]["btech"] + data["programs"]["me_mtech"]

    checks = [
        (website, "Official website missing in document"),
        (admissions_portal, "Admissions portal missing in document"),
        (email, "Admissions email missing in document"),
        (document_link, "Official admission document PDF link missing in document"),
    ]

    for value, message in checks:
        if not _contains(document, value):
            failures.append(message)

    for phone in phones:
        if not _contains(document, phone):
            failures.append(f"Phone number missing in document: {phone}")

    for program in required_programs:
        if not _contains(document, program):
            failures.append(f"Program missing in document: {program}")

    if failures:
        print("KB VALIDATION FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("KB VALIDATION PASSED")
    print(f"Document checked: {doc_path}")
    print(f"JSON checked: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

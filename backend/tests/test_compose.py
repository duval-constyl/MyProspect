"""docker compose up must hand every setting of .env to the API container (V2 and V3 keys)."""

import re
from pathlib import Path

from app.config import Settings

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
# Host-only settings: the database URL is built for the container, the GTK folder is for Windows.
HOST_ONLY = {"database_url", "weasyprint_dll_directories"}


def api_environment() -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(r"^  api:\n(.*?)^  \w+:\n", text, re.S | re.M)
    assert match, "service api introuvable"
    return match.group(1)


def test_compose_passes_every_setting_to_api():
    section = api_environment()
    missing = [
        name.upper()
        for name in Settings.model_fields
        if name not in HOST_ONLY and not re.search(rf"^\s+{name.upper()}:", section, re.M)
    ]
    assert missing == []


def test_compose_never_passes_the_windows_dll_folder():
    assert "WEASYPRINT_DLL_DIRECTORIES" not in api_environment()

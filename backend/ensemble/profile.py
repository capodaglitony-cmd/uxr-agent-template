"""
ensemble/profile.py — owner identity + branding loader.

Reads `config/profile.yaml` at module import time and exposes the
fields the persona prompts and wizard preambles substitute in. If the
file is missing (e.g. a fresh fork that hasn't been configured yet),
falls back to neutral placeholders so prompts still compose cleanly
and the practitioner can run the harness against the `_sample/` corpus
before customizing.

Override the profile path with the UXR_PROFILE_PATH env var. Default
search order is UXR_PROFILE_PATH → config/profile.yaml relative to the
backend working directory → backend/config/profile.yaml.
"""

import os
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


_FALLBACK: Dict[str, Any] = {
    "owner": {
        "name": "the practitioner",
        "github": "",
        "specialty": "UX research",
        "bio_short": "",
        "bio_url": "",
    },
    "branding": {
        "agent_handle": "uxr-agent",
        "accent_color": "#3a7ab8",
    },
}


def _candidate_paths() -> list[Path]:
    overrides = os.environ.get("UXR_PROFILE_PATH")
    if overrides:
        return [Path(overrides)]
    return [
        Path("config/profile.yaml"),
        Path("backend/config/profile.yaml"),
        Path(__file__).resolve().parent.parent.parent / "config" / "profile.yaml",
    ]


def load_profile() -> Dict[str, Any]:
    if yaml is None:
        return _FALLBACK
    for path in _candidate_paths():
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
            except Exception:
                continue
            # Shallow-merge against fallback so missing keys still resolve.
            owner = {**_FALLBACK["owner"], **(loaded.get("owner") or {})}
            branding = {**_FALLBACK["branding"], **(loaded.get("branding") or {})}
            return {"owner": owner, "branding": branding}
    return _FALLBACK


PROFILE = load_profile()
OWNER_NAME = PROFILE["owner"]["name"]
OWNER_SPECIALTY = PROFILE["owner"]["specialty"]
OWNER_BIO_SHORT = PROFILE["owner"].get("bio_short", "")
AGENT_HANDLE = PROFILE["branding"]["agent_handle"]


def owner_possessive() -> str:
    """Return "{name}'s" with the apostrophe-s suffix.

    Handles names ending in "s" by adding just an apostrophe.
    """
    if OWNER_NAME.endswith("s"):
        return f"{OWNER_NAME}'"
    return f"{OWNER_NAME}'s"

"""
CDNLiveTV provider — API JSON pubblica.
Endpoint: https://api.cdnlivetv.tv/api/v1/channels/?user=cdnlivetv&plan=free
"""

import re
import base64
import logging
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.cdnlivetv.tv"
MIRROR = "https://api.cdnlivetv.is"
PLAYER_BASE = "https://cdnlivetv.tv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{PLAYER_BASE}/",
}


def fetch_channel_list() -> list[dict]:
    """Ritorna la lista canali dall'API."""
    for base in (API_BASE, MIRROR):
        try:
            r = requests.get(
                f"{base}/api/v1/channels/",
                params={"user": "cdnlivetv", "plan": "free"},
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                logger.info("CDNLiveTV: %d canali", len(data))
                return data
        except Exception as e:
            logger.warning("CDNLiveTV mirror %s fallito: %s", base, e)
    raise RuntimeError("CDNLiveTV non raggiungibile")


def find_channel(channels: list[dict], query: str) -> dict | None:
    """Cerca canale per nome (match flessibile)."""
    q = query.lower().strip()

    for ch in channels:
        name = (ch.get("name") or "").lower()
        if name == q:
            return ch

    for ch in channels:
        name = (ch.get("name") or "").lower()
        if q in name:
            return ch

    words = set(q.split())
    best_score, best = 0, None
    for ch in channels:
        name_words = set((ch.get("name") or "").lower().split())
        score = len(words & name_words)
        if score > best_score:
            best_score, best = score, ch
    return best if best_score >= max(1, len(words) - 1) else None


def resolve_stream_url(channel: dict) -> str:
    """
    Dato il dict canale, fetcha la pagina player ed estrae l'm3u8.
    La pagina player contiene base64 concatenato o regex diretta.
    """
    player_url = channel.get("url")
    if not player_url:
        # costruisci: /api/v1/channels/player/?name=ESPN&code=us&...
        name = channel.get("name", "").replace(" ", "%20")
        player_url = f"{PLAYER_BASE}/api/v1/channels/player/?name={name}"

    r = requests.get(player_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    html = r.text

    # 1. Prova base64 concatenato: atob(...) + atob(...)
    b64_parts = re.findall(r'atob\(["\']([^"\']+)["\']\)', html)
    if b64_parts:
        decoded = "".join(
            base64.b64decode(p).decode("utf-8", errors="ignore")
            for p in b64_parts
        )
        m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', decoded)
        if m:
            return m.group(0)

    # 2. Fallback: regex diretta
    m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
    if m:
        return m.group(0)

    raise RuntimeError(f"m3u8 non trovato per {channel.get('name')}")


def get_stream(channel_name: str) -> dict:
    channels = fetch_channel_list()
    ch = find_channel(channels, channel_name)
    if not ch:
        raise ValueError(f"Canale '{channel_name}' non trovato su CDNLiveTV")

    url = resolve_stream_url(ch)
    return {
        "url": url,
        "headers": {
            "Referer": f"{PLAYER_BASE}/",
            "User-Agent": HEADERS["User-Agent"],
        },
        "source": "cdnlivetv",
        "channel_name": ch.get("name"),
    }

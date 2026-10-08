"""
CDNLiveTV provider - API JSON pubblica
"""

import re
import base64
import logging

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.cdnlivetv.tv"
MIRROR = "https://api.cdnlivetv.is"
PLAYER_BASE = "https://cdnlivetv.tv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": f"{PLAYER_BASE}/",
}


def fetch_channel_list() -> list:
    """Ritorna lista canali dall'API"""
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
    
    raise RuntimeError("CDNLiveTV: non raggiungibile")


def find_channel(channels: list, query: str) -> dict:
    """Cerca canale per nome con match flessibile"""
    q = query.lower().strip()
    
    # 1. Match esatto
    for ch in channels:
        if (ch.get("name") or "").lower() == q:
            return ch
    
    # 2. Query contenuta nel nome
    for ch in channels:
        if q in (ch.get("name") or "").lower():
            return ch
    
    # 3. Match parole
    words = set(q.split())
    best_score, best = 0, None
    for ch in channels:
        name_words = set((ch.get("name") or "").lower().split())
        score = len(words & name_words)
        if score > best_score:
            best_score, best = score, ch
    
    if best and best_score >= max(1, len(words) - 1):
        return best
    
    raise ValueError(f"CDNLiveTV: canale '{query}' non trovato")


def resolve_stream_url(channel: dict) -> str:
    """Estrai m3u8 dalla pagina player"""
    player_url = channel.get("url")
    if not player_url:
        name = channel.get("name", "").replace(" ", "%20")
        player_url = f"{PLAYER_BASE}/api/v1/channels/player/?name={name}"
    
    r = requests.get(player_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    html = r.text
    
    # 1. Base64 concatenato: atob(...) + atob(...)
    b64_parts = re.findall(r'atob\(["\']([^"\']+)["\']\)', html)
    if b64_parts:
        decoded = "".join(base64.b64decode(p).decode("utf-8", errors="ignore") for p in b64_parts)
        m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', decoded)
        if m:
            return m.group(0)
    
    # 2. Fallback: regex diretta
    m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
    if m:
        return m.group(0)
    
    raise RuntimeError(f"CDNLiveTV: m3u8 non trovato per {channel.get('name')}")


def get_stream(channel_name: str) -> dict:
    """API pubblica: dato nome canale, ritorna url + headers"""
    channels = fetch_channel_list()
    ch = find_channel(channels, channel_name)
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
def resolve(channel: dict, stream: dict) -> dict:
    """
    Interfaccia richiesta da generate_m3u.py
    Riceve channel e stream, ritorna dict con url e metadata.
    """
    query = stream.get("query") or channel.get("name", "")
    result = get_stream(query)
    
    return {
        "url": result["url"],
        "provider": "CDNLiveTV",
        "quality": "HD",
        "headers": result.get("headers", {}),
        "proxy": "auto",
        "proxy_required": False,
    }

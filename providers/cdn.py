"""
CDNLiveTV provider - API JSON pubblica
Funziona DIRETTO (senza proxy) perché api.cdnlivetv.tv non blocca GitHub Actions
"""

import re
import base64
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

API_BASE = "https://api.cdnlivetv.tv"
MIRROR = "https://api.cdnlivetv.is"
PLAYER_BASE = "https://cdnlivetv.tv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Origin": PLAYER_BASE,
    "Referer": f"{PLAYER_BASE}/",
}


def _get_session() -> requests.Session:
    """Crea sessione con retry automatico"""
    s = requests.Session()
    s.headers.update(HEADERS)
    
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    
    return s


def fetch_channel_list() -> list:
    """Ritorna lista canali dall'API"""
    session = _get_session()
    
    for base in (API_BASE, MIRROR):
        try:
            url = f"{base}/api/v1/channels/?user=cdnlivetv&plan=free"
            r = session.get(url, timeout=20)
            logger.info("Risposta da %s: status=%d, length=%d", base, r.status_code, len(r.text))
            r.raise_for_status()
            data = r.json()
            
            # La risposta è un dict con "channels" lista
            if isinstance(data, dict) and "channels" in data:
                channels = data["channels"]
                logger.info("CDNLiveTV: %d canali", len(channels))
                return channels
            elif isinstance(data, list) and data:
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
    
    # 3. Match parole (tutte le parole della query nel nome)
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
    session = _get_session()
    
    player_url = channel.get("url")
    if not player_url:
        name = channel.get("name", "").replace(" ", "%20")
        player_url = f"{PLAYER_BASE}/api/v1/channels/player/?name={name}"
    
    logger.info("Player URL: %s", player_url)
    r = session.get(player_url, timeout=20)
    r.raise_for_status()
    html = r.text
    
    # 1. Base64 concatenato: atob(...) + atob(...)
    b64_parts = re.findall(r'atob\(["\']([^"\']+)["\']\)', html)
    if b64_parts:
        decoded = "".join(base64.b64decode(p).decode("utf-8", errors="ignore") for p in b64_parts)
        m = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', decoded)
        if m:
            return m.group(0)
    
    # 2. Fallback: regex diretta m3u8 nell'HTML
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
    """Interfaccia richiesta da generate_m3u.py"""
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

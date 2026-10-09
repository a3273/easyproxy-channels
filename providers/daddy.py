"""
DaddyLive provider - EasyProxy risolve automaticamente lo stream
"""

import re
import logging
import os
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE = "https://dlive.sx"
MIRRORS = ["https://dlive.sx", "https://dlstreams.st"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# CACHE: lista canali caricata una sola volta
_channel_cache = None


def _proxied_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """Passa attraverso EasyProxy"""
    easyproxy_base = os.environ.get("EASYPROXY_BASE", "").rstrip("/")
    
    if easyproxy_base:
        encoded_url = quote(url, safe='')
        proxy_url = f"{easyproxy_base}/proxy/manifest.m3u8?d={encoded_url}"
        return session.get(proxy_url, **kwargs)
    else:
        return session.get(url, **kwargs)


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def fetch_channel_list(session: requests.Session) -> dict:
    """Ritorna {nome_canale: id} dalla pagina 24-7-channels"""
    global _channel_cache
    
    # Usa cache se disponibile
    if _channel_cache is not None:
        logger.info("DaddyLive: usando cache canali (%d canali)", len(_channel_cache))
        return _channel_cache
    
    for mirror in MIRRORS:
        try:
            url = f"{mirror}/24-7-channels.php"
            r = _proxied_get(session, url, timeout=30)
            r.raise_for_status()
            html = r.text
            
            pattern = re.compile(
                r'href="(?:[^"]*?/)?watch\.php\?id=(\d+)"[^>]*data-title="([^"]+)"',
                re.IGNORECASE
            )
            
            channels = {}
            for m in pattern.finditer(html):
                cid = int(m.group(1))
                name = m.group(2).strip()
                if name:
                    channels[name] = cid
            
            if channels:
                logger.info("DaddyLive: trovati %d canali", len(channels))
                _channel_cache = channels  # Salva in cache
                return channels
        except Exception as e:
            logger.warning("DaddyLive mirror %s fallito: %s", mirror, e)
    
    raise RuntimeError("DaddyLive: nessun mirror raggiungibile")


def find_channel_id(channels: dict, query: str) -> int:
    """Cerca ID canale"""
    q = query.lower().strip()
    
    for name, cid in channels.items():
        if name.lower() == q:
            return cid
    
    for name, cid in channels.items():
        if q in name.lower():
            return cid
    
    words = set(q.split())
    best_score, best_id = 0, None
    for name, cid in channels.items():
        name_words = set(name.lower().split())
        score = len(words & name_words)
        if score > best_score:
            best_score, best_id = score, cid
    
    if best_id and best_score >= max(1, len(words) - 1):
        return best_id
    
    raise ValueError(f"DaddyLive: canale '{query}' non trovato")


def get_stream(channel_name: str) -> dict:
    """API pubblica: dato nome canale, ritorna url + headers"""
    session = _get_session()
    channels = fetch_channel_list(session)
    cid = find_channel_id(channels, channel_name)
    
    easyproxy_base = os.environ.get("EASYPROXY_BASE", "").rstrip("/")
    player_url = f"{BASE}/cast/stream-{cid}.php"
    
    if easyproxy_base:
        encoded_url = quote(player_url, safe='')
        stream_url = f"{easyproxy_base}/proxy/manifest.m3u8?d={encoded_url}"
    else:
        stream_url = player_url
    
    return {
        "url": stream_url,
        "headers": {
            "Referer": f"{BASE}/",
            "User-Agent": HEADERS["User-Agent"],
        },
        "source": "daddylive",
        "channel_id": cid,
    }


def resolve(channel: dict, stream: dict) -> dict:
    """Interfaccia richiesta da generate_m3u.py"""
    query = stream.get("query") or channel.get("name", "")
    result = get_stream(query)
    
    return {
        "url": result["url"],
        "provider": "DaddyLive",
        "quality": "HD",
        "headers": result.get("headers", {}),
        "proxy": "auto",
        "proxy_required": False,
    }
    

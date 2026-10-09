"""
DaddyLive provider - scraping nativo via EasyProxy
"""

import re
import base64
import json
import logging
import os
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE = "https://dlive.sx"
MIRRORS = ["https://dlive.sx", "https://dlstreams.st"]
EMBED_BASE = "https://assetrage.net"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _proxied_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """Passa attraverso EasyProxy"""
    easyproxy_base = os.environ.get("EASYPROXY_BASE", "").rstrip("/")
    
    if easyproxy_base:
        encoded_url = quote(url, safe='')
        proxy_url = f"{easyproxy_base}/proxy/manifest.m3u8?d={encoded_url}"
        return session.get(proxy_url, **kwargs)
    else:
        return session.get(url, **kwargs)


def _decode_econfig(encoded: str) -> dict:
    """Decodifica _econfig"""
    raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
    
    for sep in ["|", ",", ";", ":"]:
        parts = raw.split(sep)
        if len(parts) == 4:
            break
    else:
        parts = re.split(r"[^A-Za-z0-9+/=]+", raw)
    
    if len(parts) != 4:
        raise ValueError(f"_econfig: attese 4 parti, trovate {len(parts)}")
    
    cleaned = [p[:3] + p[4:] if len(p) > 3 else p for p in parts]
    reordered = cleaned[2] + cleaned[0] + cleaned[3] + cleaned[1]
    decoded = base64.b64decode(reordered).decode("utf-8")
    return json.loads(decoded)


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def fetch_channel_list(session: requests.Session) -> dict:
    """Ritorna {nome_canale: id}"""
    for mirror in MIRRORS:
        try:
            url = f"{mirror}/24-7-channels.php"
            r = _proxied_get(session, url, timeout=30)
            r.raise_for_status()
            html = r.text
            
            # Regex aggiornata per data-title
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


def resolve_stream_url(channel_id: int, session: requests.Session) -> str:
    """Estrai stream URL"""
    
    # Prova tutti i pattern di player
    player_patterns = [
        f"{BASE}/cast/stream-{channel_id}.php",
        f"{BASE}/stream/stream-{channel_id}.php",
        f"{BASE}/watch/stream-{channel_id}.php",
        f"{BASE}/player/stream-{channel_id}.php",
        f"{BASE}/plus/stream-{channel_id}.php",
    ]
    
    player_html = None
    player_url = None
    
    for purl in player_patterns:
        try:
            r = _proxied_get(session, purl, timeout=20, headers={"Referer": f"{BASE}/watch.php?id={channel_id}"})
            if r.status_code == 200 and len(r.text) > 100:
                player_html = r.text
                player_url = purl
                logger.info("Player trovato: %s", purl)
                break
        except Exception as e:
            logger.debug("Player %s fallito: %s", purl, e)
    
    if not player_html:
        raise RuntimeError(f"DaddyLive: nessun player trovato per canale {channel_id}")
    
    # Cerca iframe
    m = re.search(r'iframe[^>]+src=["\'](https?://[^"\']+)["\']', player_html, re.IGNORECASE)
    if not m:
        # Prova a cercare m3u8 diretto nel player
        m3 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', player_html)
        if m3:
            return m3.group(0)
        raise RuntimeError(f"DaddyLive: nessun iframe o m3u8 in {player_url}")
    
    embed_url = m.group(1)
    
    # Fetch embed
    r2 = _proxied_get(session, embed_url, timeout=20, headers={"Referer": player_url, "Origin": BASE})
    r2.raise_for_status()
    embed_html = r2.text
    
    # Cerca _econfig
    m2 = re.search(r'_econfig\s*=\s*["\']([^"\']+)["\']', embed_html)
    if m2:
        try:
            cfg = _decode_econfig(m2.group(1))
            stream_url = cfg.get("stream_url") or cfg.get("url") or cfg.get("src")
            if stream_url:
                return stream_url
        except Exception as e:
            logger.warning("Decode _econfig fallito: %s", e)
    
    # Fallback: regex m3u8
    m3 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', embed_html)
    if m3:
        return m3.group(0)
    
    raise RuntimeError(f"DaddyLive: stream URL non trovato per canale {channel_id}")


def get_stream(channel_name: str) -> dict:
    session = _get_session()
    channels = fetch_channel_list(session)
    cid = find_channel_id(channels, channel_name)
    url = resolve_stream_url(cid, session)
    
    return {
        "url": url,
        "headers": {
            "Referer": f"{EMBED_BASE}/",
            "User-Agent": HEADERS["User-Agent"],
            "Origin": EMBED_BASE,
        },
        "source": "daddylive",
        "channel_id": cid,
    }


def resolve(channel: dict, stream: dict) -> dict:
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

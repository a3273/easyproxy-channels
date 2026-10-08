"""
DaddyLive provider - scraping nativo
Catena: 24-7-channels.php → cast/stream-{id}.php → assetrage.net/e/{token} → _econfig
"""

import re
import base64
import json
import logging
from urllib.parse import urljoin

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
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def _decode_econfig(encoded: str) -> dict:
    """Decodifica _econfig: base64 → split 4 → rimuovi char[3] → riordina [2,0,3,1] → base64 → JSON"""
    raw = base64.b64decode(encoded).decode("utf-8", errors="ignore")
    
    # Prova separatori comuni
    for sep in ["|", ",", ";", ":"]:
        parts = raw.split(sep)
        if len(parts) == 4:
            break
    else:
        # Fallback: split su qualsiasi non alfanumerico
        parts = re.split(r"[^A-Za-z0-9+/=]+", raw)
    
    if len(parts) != 4:
        raise ValueError(f"_econfig: attese 4 parti, trovate {len(parts)}")
    
    cleaned = [p[:3] + p[4:] if len(p) > 3 else p for p in parts]
    reordered = cleaned[2] + cleaned[0] + cleaned[3] + cleaned[1]
    decoded = base64.b64decode(reordered).decode("utf-8")
    return json.loads(decoded)


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


def fetch_channel_list(session: requests.Session) -> dict:
    """Ritorna {nome_canale: id} dalla pagina 24-7-channels"""
    for mirror in MIRRORS:
        try:
            url = f"{mirror}/24-7-channels.php"
            r = session.get(url, timeout=20)
            r.raise_for_status()
            html = r.text
            
            # Regex: <a href="watch.php?id=123" ...>Nome Canale</a>
            pattern = re.compile(r'href=["\']watch\.php\?id=(\d+)["\'][^>]*>([^<]+)', re.IGNORECASE)
            channels = {}
            for m in pattern.finditer(html):
                cid = int(m.group(1))
                name = m.group(2).strip()
                if name:
                    channels[name] = cid
            
            if channels:
                logger.info("DaddyLive: trovati %d canali da %s", len(channels), mirror)
                return channels
        except Exception as e:
            logger.warning("DaddyLive mirror %s fallito: %s", mirror, e)
    
    raise RuntimeError("DaddyLive: nessun mirror raggiungibile")


def find_channel_id(channels: dict, query: str) -> int:
    """Cerca ID canale con match flessibile"""
    q = query.lower().strip()
    
    # 1. Match esatto
    for name, cid in channels.items():
        if name.lower() == q:
            return cid
    
    # 2. Query contenuta nel nome
    for name, cid in channels.items():
        if q in name.lower():
            return cid
    
    # 3. Match parole
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
    """Catena completa: player → iframe → embed → _econfig → stream_url"""
    
    # 1. Player page
    player_url = f"{BASE}/cast/stream-{channel_id}.php"
    r = session.get(player_url, timeout=20, headers={"Referer": f"{BASE}/watch.php?id={channel_id}"})
    r.raise_for_status()
    
    # 2. Estrai iframe assetrage
    m = re.search(r'iframe[^>]+src=["\'](https?://assetrage\.net/e/[^"\']+)["\']', r.text, re.IGNORECASE)
    if not m:
        m = re.search(r'iframe[^>]+src=["\'](https?://[^"\']+)["\']', r.text, re.IGNORECASE)
    if not m:
        raise RuntimeError(f"DaddyLive: nessun iframe in {player_url}")
    
    embed_url = m.group(1)
    
    # 3. Fetch embed
    r2 = session.get(embed_url, timeout=20, headers={"Referer": player_url, "Origin": BASE})
    r2.raise_for_status()
    embed_html = r2.text
    
    # 4. Cerca _econfig
    m2 = re.search(r'_econfig\s*=\s*["\']([^"\']+)["\']', embed_html)
    if m2:
        cfg = _decode_econfig(m2.group(1))
        stream_url = cfg.get("stream_url") or cfg.get("url") or cfg.get("src")
        if stream_url:
            return stream_url
    
    # 5. Fallback: regex diretta m3u8
    m3 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', embed_html)
    if m3:
        return m3.group(0)
    
    raise RuntimeError(f"DaddyLive: stream URL non trovato per canale {channel_id}")


def get_stream(channel_name: str) -> dict:
    """API pubblica: dato nome canale, ritorna url + headers"""
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
    """
    Interfaccia richiesta da generate_m3u.py
    Riceve channel e stream, ritorna dict con url e metadata.
    """
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

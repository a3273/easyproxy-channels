"""
DaddyLive provider - tentativo avanzato senza proxy
Simula browser completo con cookie, redirect e header
"""

import re
import logging
import http.cookiejar
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE = "https://dlive.sx"
MIRRORS = ["https://dlive.sx", "https://dlstreams.st"]

# Header completi da browser reale
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}

_channel_cache = None


def _get_session() -> requests.Session:
    """Sessione con cookie jar e redirect automatici"""
    
    # Cookie jar per gestire sessioni
    jar = http.cookiejar.CookieJar()
    
    s = requests.Session()
    s.cookies = jar
    s.headers.update(HEADERS)
    s.allow_redirects = True
    
    # Retry aggressivo
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    
    return s


def fetch_channel_list(session: requests.Session) -> dict:
    """Ritorna {nome_canale: id} con gestione avanzata"""
    global _channel_cache

    if _channel_cache is not None:
        logger.info("DaddyLive: usando cache (%d canali)", len(_channel_cache))
        return _channel_cache

    for mirror in MIRRORS:
        try:
            # Prima visita la home per settare cookie
            logger.info("DaddyLive: visita home %s", mirror)
            session.get(mirror, timeout=15)
            
            # Poi la pagina canali
            url = f"{mirror}/24-7-channels.php"
            r = session.get(url, timeout=20)
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
                _channel_cache = channels
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
    """
    Tentativo avanzato: visita la pagina watch, poi il player,
    cerca di estrarre l'm3u8 reale con tutti i header necessari
    """
    session = _get_session()
    channels = fetch_channel_list(session)
    cid = find_channel_id(channels, channel_name)
    
    # Step 1: Visita pagina watch per settare cookie di sessione
    watch_url = f"{BASE}/watch.php?id={cid}"
    logger.info("DaddyLive: visita watch %s", watch_url)
    
    try:
        r_watch = session.get(watch_url, timeout=15)
        r_watch.raise_for_status()
    except Exception as e:
        logger.warning("DaddyLive: watch page fallita: %s", e)
    
    # Step 2: Prova a ottenere il player con header Referer corretto
    player_url = f"{BASE}/cast/stream-{cid}.php"
    
    headers_player = HEADERS.copy()
    headers_player.update({
        "Referer": watch_url,
        "Origin": BASE,
        "Sec-Fetch-Site": "same-origin",
    })
    
    logger.info("DaddyLive: richiesta player %s", player_url)
    
    try:
        r_player = session.get(
            player_url, 
            headers=headers_player, 
            timeout=20,
            allow_redirects=True
        )
        r_player.raise_for_status()
        
        content_type = r_player.headers.get('Content-Type', '')
        logger.info("DaddyLive: player content-type %s", content_type)
        
        # Se è già m3u8, perfetto
        if 'mpegurl' in content_type or 'm3u8' in content_type:
            logger.info("DaddyLive: URL diretto m3u8 trovato")
            return {
                "url": player_url,
                "headers": {
                    "Referer": watch_url,
                    "User-Agent": HEADERS["User-Agent"],
                    "Origin": BASE,
                },
                "source": "daddylive",
                "channel_id": cid,
            }
        
        # Altrimenti cerca m3u8 nell'HTML
        html = r_player.text
        
        # Pattern vari per m3u8
        m3u8_patterns = [
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source\s*:\s*["\']([^"\']+)["\']',
            r'file\s*:\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in m3u8_patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                stream_url = m.group(1)
                # Se è relativo, rendilo assoluto
                if stream_url.startswith('/'):
                    stream_url = urljoin(BASE, stream_url)
                
                logger.info("DaddyLive: m3u8 trovato nell'HTML")
                return {
                    "url": stream_url,
                    "headers": {
                        "Referer": player_url,
                        "User-Agent": HEADERS["User-Agent"],
                        "Origin": BASE,
                    },
                    "source": "daddylive",
                    "channel_id": cid,
                }
        
        # Ultimo tentativo: cerca iframe e visita
        m_iframe = re.search(
            r'iframe[^>]+src=["\'](https?://[^"\']+)["\']', 
            html, 
            re.IGNORECASE
        )
        
        if m_iframe:
            iframe_url = m_iframe.group(1)
            logger.info("DaddyLive: iframe trovato %s", iframe_url)
            
            r_iframe = session.get(
                iframe_url,
                headers={
                    "Referer": player_url,
                    "User-Agent": HEADERS["User-Agent"],
                },
                timeout=20
            )
            r_iframe.raise_for_status()
            
            # Cerca m3u8 nell'iframe
            iframe_html = r_iframe.text
            m3 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', iframe_html)
            if m3:
                return {
                    "url": m3.group(0),
                    "headers": {
                        "Referer": iframe_url,
                        "User-Agent": HEADERS["User-Agent"],
                    },
                    "source": "daddylive",
                    "channel_id": cid,
                }
        
        # Se tutto fallisce, ritorna URL player diretto (forse il player lo gestisce)
        logger.warning("DaddyLive: nessun m3u8 trovato, uso URL player diretto")
        return {
            "url": player_url,
            "headers": {
                "Referer": watch_url,
                "User-Agent": HEADERS["User-Agent"],
                "Origin": BASE,
            },
            "source": "daddylive",
            "channel_id": cid,
        }
        
    except Exception as e:
        logger.error("DaddyLive: errore get_stream: %s", e)
        raise


def resolve(channel: dict, stream: dict) -> dict:
    query = stream.get("query") or channel.get("name", "")
    result = get_stream(query)

    return {
        "url": result["url"],
        "provider": "DaddyLive",
        "quality": "HD",
        "headers": result.get("headers", {}),
        "proxy": "direct",
        "proxy_required": False,
    }

import json
import os
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT = 20


def _clean(value) -> str:
    return str(value or "").strip()


def _validate_url(url: str) -> str:
    url = _clean(url)

    if not url:
        raise ValueError("URL vuoto")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL non valido: {url}")

    return url


def _request_json(url: str) -> object:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; ChannelResolver/1.0)"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urlopen(
        request,
        timeout=DEFAULT_TIMEOUT
    ) as response:
        body = response.read().decode(
            "utf-8",
            errors="replace"
        )

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "La sorgente di discovery non ha restituito JSON valido"
        ) from exc


def _find_channel(data, wanted_name: str):
    """
    Cerca ricorsivamente il canale in un catalogo JSON.
    """

    wanted = wanted_name.casefold().strip()

    def walk(node):

        if isinstance(node, dict):

            possible_name = _clean(
                node.get("name")
                or node.get("title")
                or node.get("channel_name")
                or node.get("channel")
            )

            possible_url = _clean(
                node.get("url")
                or node.get("stream_url")
                or node.get("streamUrl")
                or node.get("m3u8")
                or node.get("stream")
            )

            status = _clean(
                node.get("status")
            ).casefold()

            # Se il catalogo fornisce lo stato,
            # preferiamo i canali online.
            online_ok = (
                not status
                or status in {
                    "online",
                    "live",
                    "active",
                    "available"
                }
            )

            if (
                possible_name
                and possible_name.casefold().strip() == wanted
                and possible_url
                and online_ok
            ):
                return {
                    "name": possible_name,
                    "url": possible_url,
                    "headers": node.get(
                        "headers",
                        {}
                    ),
                }

            for value in node.values():

                result = walk(value)

                if result:
                    return result

        elif isinstance(node, list):

            for item in node:

                result = walk(item)

                if result:
                    return result

        return None

    return walk(data)


def _discover(channel_name: str, stream: dict) -> dict:
    """
    Discovery autorizzata.

    Priorità:
    1. resolver_url nello stream
    2. CDN_CATALOG_URL nelle variabili ambiente
    """

    resolver_url = _clean(
        stream.get("resolver_url")
    )

    catalog_url = _clean(
        os.getenv("CDN_CATALOG_URL")
    )

    endpoint = resolver_url or catalog_url

    if not endpoint:
        raise ValueError(
            "Nessuna sorgente di discovery configurata per CDNLiveTV. "
            "Imposta CDN_CATALOG_URL oppure resolver_url nello stream."
        )

    discovery_url = (
        f"{endpoint}"
        f"{'&' if '?' in endpoint else '?'}"
        f"channel={quote(channel_name)}"
    )

    data = _request_json(
        discovery_url
    )

    match = _find_channel(
        data,
        channel_name
    )

    if not match:
        raise ValueError(
            f"Canale non trovato nel catalogo CDN: "
            f"{channel_name}"
        )

    return match


def resolve(channel: dict, stream: dict) -> dict:

    if not isinstance(channel, dict):
        raise TypeError(
            "channel deve essere un dict"
        )

    if not isinstance(stream, dict):
        raise TypeError(
            "stream deve essere un dict"
        )

    channel_name = _clean(
        channel.get("name")
    )

    if not channel_name:
        raise ValueError(
            "Nome canale mancante"
        )

    # URL esplicito, quando disponibile.
    source_url = _clean(
        stream.get("url")
    )

    headers = {}

    if source_url:

        resolved_url = _validate_url(
            source_url
        )

    else:

        result = _discover(
            channel_name,
            stream
        )

        resolved_url = _validate_url(
            result.get("url")
        )

        if isinstance(
            result.get("headers"),
            dict
        ):
            headers = result["headers"]

    print(
        f"[CDNLIVETV] "
        f"{channel_name} -> {resolved_url}"
    )

    return {
        "url": resolved_url,
        "provider": "CDNLiveTV",
        "quality": "HD",
        "priority": int(
            stream.get(
                "priority",
                2
            )
        ),
        "proxy": stream.get(
            "proxy",
            "auto"
        ),
        "proxy_required": False,
        "headers": headers,
    }

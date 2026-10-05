from urllib.parse import urlparse


def _validate_url(url: str) -> str:
    url = str(url or "").strip()

    if not url:
        raise ValueError("URL sorgente vuoto")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL non valido: {url}")

    return url


def resolve(channel: dict, stream: dict) -> dict:
    if not isinstance(channel, dict):
        raise TypeError("channel deve essere un dict")

    if not isinstance(stream, dict):
        raise TypeError("stream deve essere un dict")

    channel_name = str(
        channel.get("name", "")
    ).strip()

    source_url = _validate_url(
        stream.get("url", "")
    )

    print(
        f"[DADDYLIVE] "
        f"channel={channel_name} "
        f"url={source_url}"
    )

    return {
        "url": source_url,
        "provider": "Daddy",
        "quality": "HD",
        "priority": int(
            stream.get("priority", 1)
        ),
        "proxy": stream.get(
            "proxy",
            "auto"
        ),
        "proxy_required": False,
        "headers": {}
    }

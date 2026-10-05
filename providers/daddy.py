from urllib.parse import urlparse


def _validate_url(value: str) -> str:
    value = str(value or "").strip()

    if not value:
        raise ValueError("URL sorgente vuoto")

    parsed = urlparse(value)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL non valido: {value}")

    return value


def resolve(channel: dict, stream: dict) -> dict:
    """
    Resolver generico per una sorgente autorizzata.

    In questa versione l'URL viene fornito dal record dello stream.
    La parte di discovery specifica del provider va collegata
    separatamente per sorgenti per cui si dispone dell'autorizzazione.
    """

    if not isinstance(channel, dict):
        raise TypeError("channel deve essere un dict")

    if not isinstance(stream, dict):
        raise TypeError("stream deve essere un dict")

    channel_name = str(channel.get("name", "")).strip()
    source_url = _validate_url(stream.get("url", ""))

    print(
        f"[DADDY_PROVIDER] channel={channel_name} url={source_url}"
    )

    return {
        "url": source_url,
        "provider": "Daddy",
        "quality": "HD",
        "priority": int(stream.get("priority", 1)),
        "proxy": stream.get("proxy", "auto"),
        "proxy_required": False,
        "headers": {}
    }

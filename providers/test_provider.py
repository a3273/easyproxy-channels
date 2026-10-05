from urllib.parse import urlparse


def resolve(channel: dict, stream: dict) -> dict:
    source_url = str(
        stream.get("url", "")
    ).strip()

    if not source_url:
        raise ValueError(
            "URL test mancante"
        )

    parsed = urlparse(source_url)

    if parsed.scheme not in (
        "http",
        "https"
    ):
        raise ValueError(
            "URL test non valido"
        )

    return {
        "url": source_url,
        "provider": "Test",
        "quality": "HD",
        "priority": int(
            stream.get(
                "priority",
                1
            )
        ),
        "proxy": "direct",
        "proxy_required": False,
        "headers": {}
    }

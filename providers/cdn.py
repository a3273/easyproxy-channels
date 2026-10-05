from urllib.parse import urlparse


def resolve(source_url: str) -> dict:

    parsed = urlparse(
        source_url
    )

    if parsed.scheme not in (
        "http",
        "https"
    ):
        raise ValueError(
            "URL non valido"
        )

    print(
        f"[CDN_PROVIDER] "
        f"Risolvo: {source_url}"
    )

    return {
        "url": source_url,
        "provider": "CDN",
        "quality": "HD",
        "priority": 2,

        "proxy": "auto",
        "proxy_required": False,

        "headers": {}
    }

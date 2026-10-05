from urllib.parse import urlparse


def resolve(source_url: str) -> dict:
    parsed = urlparse(source_url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL non valido")

    return {
        "url": source_url,
        "headers": {}
    }

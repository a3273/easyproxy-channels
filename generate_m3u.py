import importlib
import json
from pathlib import Path
from urllib.parse import quote


CHANNELS_FILE = Path("channels.json")
PLAYLIST_FILE = Path("playlist.m3u")
STATUS_FILE = Path("status.json")


def clean(value) -> str:
    return str(value or "").strip()


def m3u_escape(value: str) -> str:
    return clean(value).replace('"', "'")


def normalize_proxy_policy(value, default="auto") -> str:
    value = clean(value).lower()

    if value in {"direct", "proxy", "auto"}:
        return value

    return default


def choose_playback_mode(
    stream: dict,
    result: dict,
    default_proxy: str
) -> str:

    stream_policy = normalize_proxy_policy(
        stream.get("proxy"),
        default_proxy
    )

    provider_policy = normalize_proxy_policy(
        result.get("proxy"),
        "auto"
    )

    if stream_policy == "direct":
        return "direct"

    if stream_policy == "proxy":
        return "proxy"

    if provider_policy == "direct":
        return "direct"

    if provider_policy == "proxy":
        return "proxy"

    if result.get("proxy_required") is True:
        return "proxy"

    return "direct"


def make_playback_url(
    url: str,
    mode: str,
    easyproxy_base: str
) -> str:

    url = clean(url)

    if not url:
        raise ValueError("URL playback vuoto")

    if mode == "direct":
        return url

    if mode == "proxy":
        base = clean(easyproxy_base).rstrip("/")

        if not base:
            raise ValueError(
                "easyproxy_base non configurato"
            )

        return (
            f"{base}/proxy/manifest.m3u8?d="
            f"{quote(url, safe='')}"
        )

    raise ValueError(
        f"Modalità playback non valida: {mode}"
    )


def load_config() -> dict:
    if not CHANNELS_FILE.exists():
        raise FileNotFoundError(
            f"File non trovato: {CHANNELS_FILE}"
        )

    with CHANNELS_FILE.open(
        "r",
        encoding="utf-8"
    ) as handle:
        return json.load(handle)


def load_provider(name: str):
    module_name = (
        f"providers.{clean(name).lower()}"
    )

    return importlib.import_module(module_name)


def write_status(status: dict):
    with STATUS_FILE.open(
        "w",
        encoding="utf-8"
    ) as handle:
        json.dump(
            status,
            handle,
            indent=2,
            ensure_ascii=False
        )


def main():
    config = load_config()

    easyproxy_base = clean(
        config.get("easyproxy_base")
    )

    default_proxy = normalize_proxy_policy(
        config.get("default_proxy"),
        "auto"
    )

    channels = config.get("channels", [])

    if not isinstance(channels, list):
        raise ValueError(
            '"channels" deve essere una lista'
        )

    output = ["#EXTM3U"]

    status = {
        "summary": {
            "channels_total": 0,
            "channels_enabled": 0,
            "streams_total": 0,
            "streams_generated": 0,
            "streams_failed": 0
        },
        "channels": {}
    }

    for channel in channels:

        if not isinstance(channel, dict):
            continue

        channel_name = clean(
            channel.get("name")
        )

        if not channel_name:
            continue

        status["summary"]["channels_total"] += 1

        if channel.get("enabled", True) is not True:
            status["channels"][channel_name] = {
                "enabled": False,
                "streams": []
            }
            continue

        status["summary"]["channels_enabled"] += 1

        streams = channel.get("streams", [])

        if not isinstance(streams, list):
            streams = []

        channel_status = {
            "enabled": True,
            "streams": []
        }

        resolved_streams = []

        for stream in streams:

            if not isinstance(stream, dict):
                continue

            if stream.get("enabled", True) is not True:
                continue

            status["summary"]["streams_total"] += 1

            stream_name = clean(
                stream.get("name")
            )

            provider_name = clean(
                stream.get("provider")
            ).lower()

            source_url = clean(
                stream.get("url")
            )

            stream_status = {
                "name": stream_name,
                "provider": provider_name,
                "priority": stream.get(
                    "priority",
                    999
                ),
                "source_url_configured": bool(
                    source_url
                )
            }

            try:
                print(
                    f"[RESOLVE] "
                    f"{channel_name} / "
                    f"{stream_name} / "
                    f"provider={provider_name or 'DIRECT'} / "
                    f"url_configured="
                    f"{bool(source_url)}"
                )

                if provider_name:
                    provider = load_provider(
                        provider_name
                    )

                    # IMPORTANTE:
                    # il provider riceve sempre channel + stream.
                    # source_url può essere vuoto: il provider può
                    # effettuare discovery dinamico.
                    result = provider.resolve(
                        channel,
                        stream
                    )
                elif source_url:
                    # URL già configurato: non serve alcun provider.
                    # Questo consente di usare direttamente una sorgente
                    # autorizzata/demo senza passare da discovery.
                    result = {
                        "url": source_url,
                        "provider": stream_name or "Direct",
                        "quality": "HD",
                        "priority": stream.get("priority", 999),
                        "proxy": stream.get("proxy", default_proxy),
                        "proxy_required": False,
                        "headers": {}
                    }
                else:
                    raise ValueError(
                        "provider mancante e URL sorgente vuoto"
                    )

                if not isinstance(result, dict):
                    raise ValueError(
                        "Il provider non ha restituito un dict"
                    )

                resolved_url = clean(
                    result.get("url")
                )

                print(
                    f"[RESOLVE RESULT] "
                    f"{channel_name} / "
                    f"{stream_name} -> "
                    f"{bool(resolved_url)}"
                )

                if not resolved_url:
                    raise ValueError(
                        "Il provider non ha restituito un URL"
                    )

                mode = choose_playback_mode(
                    stream,
                    result,
                    default_proxy
                )

                playback_url = make_playback_url(
                    resolved_url,
                    mode,
                    easyproxy_base
                )

                priority = int(
                    stream.get(
                        "priority",
                        result.get(
                            "priority",
                            999
                        )
                    )
                )

                resolved_streams.append({
                    "stream": stream,
                    "result": result,
                    "priority": priority,
                    "mode": mode,
                    "url": playback_url
                })

                stream_status.update({
                    "status": "resolved",
                    "mode": mode,
                    "url": playback_url,
                    "resolved_url": resolved_url
                })

                status["summary"][
                    "streams_generated"
                ] += 1

            except Exception as exc:

                print(
                    f"[RESOLVE ERROR] "
                    f"{channel_name} / "
                    f"{stream_name}: "
                    f"{exc}"
                )

                stream_status["status"] = "error"
                stream_status["error"] = str(exc)

                status["summary"][
                    "streams_failed"
                ] += 1

            channel_status["streams"].append(
                stream_status
            )

        resolved_streams.sort(
            key=lambda item: item["priority"]
        )

        seen = set()

        for item in resolved_streams:

            result = item["result"]
            stream = item["stream"]
            mode = item["mode"]
            playback_url = item["url"]

            provider_label = clean(
                result.get(
                    "provider",
                    stream.get(
                        "name",
                        "Provider"
                    )
                )
            )

            quality = clean(
                result.get(
                    "quality",
                    "HD"
                )
            )

            stream_key = (
                channel_name,
                provider_label,
                playback_url
            )

            if stream_key in seen:
                continue

            seen.add(stream_key)

            tvg_id = m3u_escape(
                channel.get(
                    "tvg_id",
                    channel_name
                )
            )

            tvg_name = m3u_escape(
                channel_name
            )

            tvg_logo = m3u_escape(
                channel.get(
                    "tvg_logo",
                    ""
                )
            )

            group = m3u_escape(
                channel.get(
                    "group",
                    "Live TV"
                )
            )

            label = (
                f"{channel_name} "
                f"[{provider_label}] "
                f"[{quality}] "
                f"[{mode.upper()}]"
            )

            output.append(
                '#EXTINF:-1 '
                f'tvg-id="{tvg_id}" '
                f'tvg-name="{tvg_name}" '
                f'tvg-logo="{tvg_logo}" '
                f'group-title="{group}",'
                f'{m3u_escape(label)}'
            )

            headers = result.get(
                "headers",
                {}
            )

            if isinstance(headers, dict):

                user_agent = clean(
                    headers.get(
                        "User-Agent"
                    )
                )

                referrer = clean(
                    headers.get(
                        "Referer"
                    )
                )

                if user_agent:
                    output.append(
                        "#EXTVLCOPT:http-user-agent="
                        + user_agent
                    )

                if referrer:
                    output.append(
                        "#EXTVLCOPT:http-referrer="
                        + referrer
                    )

            output.append(
                playback_url
            )

        status["channels"][channel_name] = (
            channel_status
        )

    with PLAYLIST_FILE.open(
        "w",
        encoding="utf-8",
        newline="\n"
    ) as handle:
        handle.write(
            "\n".join(output) + "\n"
        )

    write_status(status)

    print(
        "----------------------------------------"
    )

    print("M3U generation completed")

    print(
        f"Channels: "
        f"{status['summary']['channels_enabled']}/"
        f"{status['summary']['channels_total']}"
    )

    print(
        f"Streams generated: "
        f"{status['summary']['streams_generated']}"
    )

    print(
        f"Streams failed: "
        f"{status['summary']['streams_failed']}"
    )

    print(
        f"Playlist: {PLAYLIST_FILE}"
    )

    print(
        f"Status: {STATUS_FILE}"
    )

    print(
        "----------------------------------------"
    )


if __name__ == "__main__":
    main()

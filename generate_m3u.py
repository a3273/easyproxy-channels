import importlib
import json
from urllib.parse import quote


CHANNELS_FILE = "channels.json"
PLAYLIST_FILE = "playlist.m3u"
STATUS_FILE = "status.json"


def clean(value):
    return str(value or "").strip()


def m3u_escape(value):
    return clean(value).replace('"', "'")


def normalize_proxy_policy(value):
    if isinstance(value, bool):
        return "proxy" if value else "direct"

    value = clean(value).lower()

    if value in {"true", "yes", "1", "proxy"}:
        return "proxy"

    if value in {"false", "no", "0", "direct"}:
        return "direct"

    return "auto"


def choose_playback_mode(stream_policy, provider_result):
    policy = normalize_proxy_policy(stream_policy)

    provider_policy = normalize_proxy_policy(
        provider_result.get("proxy", "auto")
    )

    proxy_required = bool(
        provider_result.get("proxy_required", False)
    )

    if policy in {"direct", "proxy"}:
        return policy

    if provider_policy in {"direct", "proxy"}:
        return provider_policy

    return "proxy" if proxy_required else "direct"


def make_playback_url(source_url, mode, base):
    if mode == "proxy":
        return (
            f"{base}/proxy/manifest.m3u8?d="
            + quote(source_url, safe="")
        )

    return source_url


with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


base = clean(
    data["easyproxy_base"]
).rstrip("/")

default_proxy = normalize_proxy_policy(
    data.get("default_proxy", "auto")
)


lines = ["#EXTM3U"]

seen_streams = set()

status = {
    "generated": 0,
    "skipped": 0,
    "errors": 0,
    "channels": []
}


for channel in data.get("channels", []):

    name = clean(
        channel.get("name")
    )

    group = clean(
        channel.get(
            "group",
            "Other"
        )
    )

    tvg_id = clean(
        channel.get("tvg_id")
    )

    logo = clean(
        channel.get("tvg_logo")
    )

    channel_status = {
        "name": name,
        "status": "ok",
        "generated": 0,
        "streams": []
    }


    if not channel.get(
        "enabled",
        True
    ):

        print(
            f"[DISABLED] {name}"
        )

        channel_status["status"] = "disabled"

        status["skipped"] += 1

        status["channels"].append(
            channel_status
        )

        continue


    resolved_streams = []


    for stream in channel.get(
        "streams",
        []
    ):

        stream_name = clean(
            stream.get(
                "name",
                "Stream"
            )
        )

        provider_name = clean(
            stream.get(
                "provider"
            )
        )

        source = clean(
            stream.get("url")
        )


        stream_status = {
            "name": stream_name,
            "provider": provider_name,
            "source_configured": bool(source)
        }

        channel_status[
            "streams"
        ].append(
            stream_status
        )


        if not stream.get(
            "enabled",
            True
        ):

            print(
                f"[SKIP] {name} / "
                f"{stream_name}: disabled"
            )

            stream_status[
                "status"
            ] = "disabled"

            status[
                "skipped"
            ] += 1

            continue


        if not source:

            print(
                f"[SKIP] {name} / "
                f"{stream_name}: "
                f"URL non ancora impostato"
            )

            stream_status[
                "status"
            ] = "not_configured"

            status[
                "skipped"
            ] += 1

            continue


        if not provider_name:

            print(
                f"[ERROR] {name} / "
                f"{stream_name}: "
                f"provider mancante"
            )

            stream_status[
                "status"
            ] = "error"

            stream_status[
                "error"
            ] = "provider mancante"

            status[
                "errors"
            ] += 1

            continue


        try:

            module = importlib.import_module(
                f"providers.{provider_name}"
            )

            result = module.resolve(
                source
            )

            resolved_url = clean(
                result.get("url")
            )

            if not resolved_url:

                raise ValueError(
                    "Il provider non ha "
                    "restituito un URL"
                )


            try:

                priority = int(
                    result.get(
                        "priority",
                        stream.get(
                            "priority",
                            999
                        )
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                priority = 999


            stream_policy = stream.get(
                "proxy",
                channel.get(
                    "proxy",
                    default_proxy
                )
            )

            playback_mode = choose_playback_mode(
                stream_policy,
                result
            )

            playback_url = make_playback_url(
                resolved_url,
                playback_mode,
                base
            )


            resolved_streams.append(
                {
                    "name": stream_name,

                    "provider": clean(
                        result.get(
                            "provider",
                            stream_name
                        )
                    ),

                    "quality": clean(
                        result.get(
                            "quality",
                            "Unknown"
                        )
                    ),

                    "priority": priority,

                    "url": playback_url,

                    "source_url": resolved_url,

                    "playback_mode": playback_mode,

                    "headers": result.get(
                        "headers",
                        {}
                    ) or {}
                }
            )


            stream_status[
                "status"
            ] = "ok"

            stream_status[
                "quality"
            ] = clean(
                result.get(
                    "quality",
                    "Unknown"
                )
            )

            stream_status[
                "priority"
            ] = priority

            stream_status[
                "playback_mode"
            ] = playback_mode


            print(
                f"[OK] {name} / "
                f"{stream_name} "
                f"-> "
                f"{playback_mode.upper()}"
            )


        except Exception as error:

            print(
                f"[ERROR] {name} / "
                f"{stream_name}: "
                f"{error}"
            )

            stream_status[
                "status"
            ] = "error"

            stream_status[
                "error"
            ] = str(error)

            status[
                "errors"
            ] += 1


    resolved_streams.sort(
        key=lambda item:
        item["priority"]
    )


    for stream in resolved_streams:

        duplicate_key = (
            name,
            stream["provider"],
            stream["url"]
        )


        if duplicate_key in seen_streams:

            print(
                f"[DUPLICATE] {name} / "
                f"{stream['provider']}"
            )

            continue


        seen_streams.add(
            duplicate_key
        )


        display_name = (
            f"{name} "
            f"[{stream['provider']}] "
            f"[{stream['quality']}] "
            f"[{stream['playback_mode'].upper()}]"
        )


        lines.append(
            f'#EXTINF:-1 '
            f'tvg-id="{m3u_escape(tvg_id)}" '
            f'tvg-name="{m3u_escape(name)}" '
            f'tvg-logo="{m3u_escape(logo)}" '
            f'group-title="{m3u_escape(group)}",'
            f'{display_name}'
        )


        headers = stream[
            "headers"
        ]


        if (
            stream["playback_mode"]
            == "direct"
        ):

            user_agent = clean(
                headers.get(
                    "User-Agent"
                )
            )

            referer = clean(
                headers.get(
                    "Referer"
                )
            )


            if user_agent:

                lines.append(
                    "#EXTVLCOPT:"
                    "http-user-agent="
                    + user_agent
                )


            if referer:

                lines.append(
                    "#EXTVLCOPT:"
                    "http-referrer="
                    + referer
                )


        lines.append(
            stream["url"]
        )


        status[
            "generated"
        ] += 1

        channel_status[
            "generated"
        ] += 1


    status[
        "channels"
    ].append(
        channel_status
    )


with open(
    PLAYLIST_FILE,
    "w",
    encoding="utf-8"
) as f:

    f.write(
        "\n".join(lines)
        + "\n"
    )


with open(
    STATUS_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        status,
        f,
        indent=2,
        ensure_ascii=False
    )


print()

print(
    "========================================"
)

print(
    "Generazione completata"
)

print(
    f"Stream generati : "
    f"{status['generated']}"
)

print(
    f"Stream saltati  : "
    f"{status['skipped']}"
)

print(
    f"Errori          : "
    f"{status['errors']}"
)

print(
    f"Output          : "
    f"{PLAYLIST_FILE}"
)

print(
    f"Report           : "
    f"{STATUS_FILE}"
)

print(
    "========================================"
)

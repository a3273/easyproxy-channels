import json
import importlib
from urllib.parse import quote


CHANNELS_FILE = "channels.json"
PLAYLIST_FILE = "playlist.m3u"
STATUS_FILE = "status.json"


def clean(value):
    return str(value or "").strip()


def m3u_escape(value):
    return clean(value).replace('"', "'")


with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)


base = clean(data["easyproxy_base"]).rstrip("/")

lines = ["#EXTM3U"]
status = {
    "generated": 0,
    "skipped": 0,
    "errors": 0,
    "channels": []
}

seen_streams = set()


for channel in data.get("channels", []):
    name = clean(channel.get("name"))
    group = clean(channel.get("group", "Other"))
    tvg_id = clean(channel.get("tvg_id"))
    logo = clean(channel.get("tvg_logo"))

    channel_status = {
        "name": name,
        "streams": []
    }

    if not channel.get("enabled", True):
        print(f"[DISABLED] {name}")

        channel_status["status"] = "disabled"
        status["skipped"] += 1
        status["channels"].append(channel_status)
        continue

    resolved_streams = []

    for stream in channel.get("streams", []):
        stream_name = clean(stream.get("name", "Stream"))
        provider_name = clean(stream.get("provider"))
        source = clean(stream.get("url"))

        stream_status = {
            "name": stream_name,
            "provider": provider_name,
            "source_configured": bool(source)
        }

        channel_status["streams"].append(stream_status)

        if not stream.get("enabled", True):
            print(
                f"[SKIP] {name} / {stream_name}: disabled"
            )
            status["skipped"] += 1
            continue

        if not source:
            print(
                f"[SKIP] {name} / {stream_name}: "
                f"URL non ancora impostato"
            )
            status["skipped"] += 1
            continue

        if not provider_name:
            print(
                f"[ERROR] {name} / {stream_name}: "
                f"provider mancante"
            )
            stream_status["status"] = "error"
            stream_status["error"] = "provider mancante"
            status["errors"] += 1
            continue

        try:
            module = importlib.import_module(
                f"providers.{provider_name}"
            )

            result = module.resolve(source)

            resolved_url = clean(result.get("url"))

            if not resolved_url:
                raise ValueError(
                    "Il provider non ha restituito un URL"
                )

            priority = result.get(
                "priority",
                stream.get("priority", 999)
            )

            try:
                priority = int(priority)
            except (TypeError, ValueError):
                priority = 999

            resolved_streams.append({
                "name": stream_name,
                "provider": clean(
                    result.get("provider", stream_name)
                ),
                "quality": clean(
                    result.get("quality", "Unknown")
                ),
                "priority": priority,
                "url": resolved_url
            })

            stream_status["status"] = "ok"
            stream_status["quality"] = clean(
                result.get("quality", "Unknown")
            )
            stream_status["priority"] = priority

            print(
                f"[OK] {name} / {stream_name}"
            )

        except Exception as error:
            print(
                f"[ERROR] {name} / {stream_name}: "
                f"{error}"
            )

            stream_status["status"] = "error"
            stream_status["error"] = str(error)

            status["errors"] += 1

    # Priorità più bassa = migliore
    resolved_streams.sort(
        key=lambda item: item["priority"]
    )

    for stream in resolved_streams:
        if stream["url"] in seen_urls:
            print(
                f"[DUPLICATE] {name} / "
                f"{stream['provider']}"
            )
            continue

        seen_urls.add(stream["url"])

        proxied_url = (
            f"{base}/proxy/manifest.m3u8?d="
            + quote(stream["url"], safe="")
        )

        display_name = (
            f"{name} "
            f"[{stream['provider']}] "
            f"[{stream['quality']}]"
        )

        lines.append(
            f'#EXTINF:-1 '
            f'tvg-id="{m3u_escape(tvg_id)}" '
            f'tvg-name="{m3u_escape(name)}" '
            f'tvg-logo="{m3u_escape(logo)}" '
            f'group-title="{m3u_escape(group)}",'
            f'{display_name}'
        )

        lines.append(proxied_url)

        status["generated"] += 1

    channel_status["generated"] = len(
        resolved_streams
    )

    status["channels"].append(channel_status)


with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")


with open(STATUS_FILE, "w", encoding="utf-8") as f:
    json.dump(
        status,
        f,
        indent=2,
        ensure_ascii=False
    )


print()
print("========================================")
print("Generazione completata")
print(f"Stream generati : {status['generated']}")
print(f"Stream saltati  : {status['skipped']}")
print(f"Errori          : {status['errors']}")
print(f"Output          : {PLAYLIST_FILE}")
print(f"Report           : {STATUS_FILE}")
print("========================================")

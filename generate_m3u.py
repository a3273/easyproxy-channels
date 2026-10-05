import json
import importlib
from urllib.parse import quote

with open("channels.json", "r", encoding="utf-8") as f:
    data = json.load(f)

base = data["easyproxy_base"].rstrip("/")

generated_count = 0
lines = ["#EXTM3U"]

for channel in data["channels"]:
    name = channel["name"]
    group = channel.get("group", "Other")
    tvg_id = channel.get("tvg_id", "")
    logo = channel.get("tvg_logo", "")

    resolved_streams = []

    for stream in channel.get("streams", []):
        stream_name = stream.get("name", "Stream")
        source = stream.get("url", "").strip()
        provider_name = stream.get("provider")

        # Salta gli stream senza URL
        if not source:
            print(
                f"[SKIP] {name} / {stream_name}: URL non ancora impostato"
            )
            continue

        if not provider_name:
            raise ValueError(
                f"Stream senza provider: {name} / {stream_name}"
            )

        module = importlib.import_module(
            f"providers.{provider_name}"
        )

        result = module.resolve(source)

        resolved_streams.append({
            "name": stream_name,
            "provider": result.get(
                "provider",
                stream_name
            ),
            "quality": result.get(
                "quality",
                "Unknown"
            ),
            "priority": result.get(
                "priority",
                999
            ),
            "url": result["url"],
            "headers": result.get(
                "headers",
                {}
            )
        })

    # Ordine: priorità più bassa = migliore
    resolved_streams.sort(
        key=lambda x: x["priority"]
    )

    for stream in resolved_streams:
        stream_url = (
            f"{base}/proxy/manifest.m3u8?d="
            + quote(stream["url"], safe="")
        )

        display_name = (
            f'{name} [{stream["provider"]}] '
            f'[{stream["quality"]}]'
        )

        lines.append(
            f'#EXTINF:-1 '
            f'tvg-id="{tvg_id}" '
            f'tvg-logo="{logo}" '
            f'group-title="{group}",'
            f'{display_name}'
        )

        lines.append(stream_url)

        generated_count += 1

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write(
        "\n".join(lines)
        + "\n"
    )

print(f"Generati {generated_count} stream.")

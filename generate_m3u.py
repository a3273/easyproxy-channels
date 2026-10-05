import json
import importlib
from urllib.parse import quote

with open("channels.json", "r", encoding="utf-8") as f:
    data = json.load(f)

base = data["easyproxy_base"].rstrip("/")

lines = ["#EXTM3U"]

for channel in data["channels"]:
    name = channel["name"]
    group = channel.get("group", "Other")
    tvg_id = channel.get("tvg_id", "")
    logo = channel.get("tvg_logo", "")

    for stream in channel.get("streams", []):
        stream_name = stream.get("name", "Stream")
        source = stream["url"]
        provider = stream.get("provider")

        if not provider:
            raise ValueError(
                f"Stream senza provider: {name} / {stream_name}"
            )

        module = importlib.import_module(f"providers.{provider}")
        result = module.resolve(source)

        resolved_url = result["url"]

        stream_url = (
            f"{base}/proxy/manifest.m3u8?d="
            + quote(resolved_url, safe="")
        )

        display_name = f"{name} [{stream_name}]"

        lines.append(
            f'#EXTINF:-1 '
            f'tvg-id="{tvg_id}" '
            f'tvg-logo="{logo}" '
            f'group-title="{group}",'
            f'{display_name}'
        )

        lines.append(stream_url)

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(
    f"Generati {sum(len(c.get('streams', [])) for c in data['channels'])} stream."
)

import json
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
    source = channel["url"]
    extractor = channel.get("extractor")

    params = []

  if extractor:
    params = [
        f"host={quote(extractor, safe='')}",
        f"d={quote(source, safe='')}",
        "redirect_stream=true",
    ]

    easyproxy_url = (
        f"{base}/extractor/video?"
        + "&".join(params)
    )
else:
    easyproxy_url = (
        f"{base}/proxy/manifest.m3u8?d="
        + quote(source, safe="")
    )

    lines.append(
        f'#EXTINF:-1 tvg-id="{tvg_id}" '
        f'tvg-logo="{logo}" '
        f'group-title="{group}",{name}'
    )
    lines.append(easyproxy_url)

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generati {len(data['channels'])} canali.")

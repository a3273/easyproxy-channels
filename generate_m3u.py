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
    source = channel["url"]
    extractor = channel.get("extractor")
    provider = channel.get("provider")

    # Se è definito un provider, lo eseguiamo.
    if provider:
        module = importlib.import_module(f"providers.{provider}")
        result = module.resolve(source)

        resolved_url = result["url"]
    else:
        resolved_url = source

    # Se c'è un extractor, usa l'endpoint extractor di EasyProxy.
    if extractor:
        params = [
            f"host={quote(extractor, safe='')}",
            f"d={quote(resolved_url, safe='')}",
            "redirect_stream=true",
        ]

        stream_url = (
            f"{base}/extractor/video?"
            + "&".join(params)
        )

    # Se non c'è extractor, usa direttamente il proxy HLS.
    else:
        stream_url = (
            f"{base}/proxy/manifest.m3u8?d="
            + quote(resolved_url, safe="")
        )

    lines.append(
        f'#EXTINF:-1 '
        f'tvg-id="{tvg_id}" '
        f'tvg-logo="{logo}" '
        f'group-title="{group}",'
        f'{name}'
    )

    lines.append(stream_url)

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generati {len(data['channels'])} canali.")

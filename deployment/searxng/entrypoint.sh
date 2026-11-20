#!/bin/sh
# Render the operator-provided search proxy into a private, container-local
# SearXNG settings file without printing the URL or its credentials.
set -eu

template="${ASTRO_SEARXNG_SETTINGS_TEMPLATE:-/etc/searxng/settings.yml}"
generated="$(mktemp /tmp/astro-searxng-settings.XXXXXX)"
trap 'rm -f "$generated"' EXIT INT TERM

if [ ! -f "$template" ]; then
    echo "SearXNG settings template is missing: $template" >&2
    exit 127
fi

/usr/local/searxng/.venv/bin/python - "$template" "$generated" <<'PY'
import json
import os
from pathlib import Path
import sys

template, generated = map(Path, sys.argv[1:])
settings = template.read_text(encoding="utf-8")
proxy = os.environ.get("LDR_SEARCH_PROXY_URL", "").strip()
if proxy:
    settings += "\noutgoing:\n  proxies:\n    all://: [" + json.dumps(proxy) + "]\n"
generated.write_text(settings, encoding="utf-8")

PY
chmod 600 "$generated"

export SEARXNG_SETTINGS_PATH="$generated"
exec /usr/local/searxng/entrypoint.sh

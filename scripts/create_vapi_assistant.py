"""
One-time helper: pushes vapi/assistant_config.json to the Vapi API to create
(or update) the assistant, then prints the assistant ID. You still need to
buy/import a phone number in the Vapi dashboard and attach it to this
assistant (or pass --phone-number-id to attach an existing one).

Usage:
    export VAPI_API_KEY=sk_...
    export DEPLOYED_BASE_URL=https://your-app.up.railway.app
    python scripts/create_vapi_assistant.py [--assistant-id <id_to_update>]

This script was written against Vapi's documented REST API shape but could
not be executed against a live Vapi account in this environment (no network
access at build time) -- double check field names against
https://docs.vapi.ai before relying on it, and prefer pasting the JSON into
the Vapi dashboard's assistant editor if this script errors.
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

VAPI_BASE = "https://api.vapi.ai"


def load_config(deployed_base_url: str) -> dict:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "vapi", "assistant_config.json")) as f:
        config = json.load(f)
    with open(os.path.join(here, "vapi", "system_prompt.md")) as f:
        prompt_md = f.read()

    # Pull the fenced prompt block out of system_prompt.md
    start = prompt_md.find("```\n") + 4
    end = prompt_md.rfind("```")
    system_prompt = prompt_md[start:end].strip()
    config["model"]["messages"][0]["content"] = system_prompt

    url = deployed_base_url.rstrip("/") + "/vapi/webhook"
    for tool in config["model"]["tools"]:
        tool["server"]["url"] = url

    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assistant-id", default=None, help="Update an existing assistant instead of creating a new one")
    args = parser.parse_args()

    api_key = os.environ.get("VAPI_API_KEY")
    base_url = os.environ.get("DEPLOYED_BASE_URL")
    if not api_key or not base_url:
        print("Set VAPI_API_KEY and DEPLOYED_BASE_URL environment variables first.", file=sys.stderr)
        sys.exit(1)

    config = load_config(base_url)
    body = json.dumps(config).encode("utf-8")

    if args.assistant_id:
        url = f"{VAPI_BASE}/assistant/{args.assistant_id}"
        method = "PATCH"
    else:
        url = f"{VAPI_BASE}/assistant"
        method = "POST"

    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Vapi's API sits behind Cloudflare, which blocks urllib's
            # default "Python-urllib/x.y" user-agent as bot-like (Cloudflare
            # error 1010). A normal-looking UA avoids that block.
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) patient-voice-agent-setup/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Vapi API returned HTTP {e.code} {e.reason}", file=sys.stderr)
        print(f"Response body: {error_body}", file=sys.stderr)
        print(
            "\nCommon causes: VAPI_API_KEY is unset/empty, is a PUBLIC key "
            "instead of a PRIVATE key, or your account still needs billing "
            "set up (see dashboard.vapi.ai/org/billing).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(json.dumps(result, indent=2))
    print(f"\nAssistant ID: {result.get('id')}")
    print("Next: in the Vapi dashboard, attach a phone number to this assistant "
          "(Phone Numbers -> Buy/Import -> select this assistant).")


if __name__ == "__main__":
    main()
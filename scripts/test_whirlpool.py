"""Layered Whirlpool API smoke test for the custom Model PoC.

Layers:
  1. OAuth client-credentials token
  2. Plain generateContent (text)
  3. generateContent with functionDeclarations (tools probe)
  4. Optional thin call through WhirlpoolModel.get_response

Env:
  WHIRLPOOL_CLIENT_ID
  WHIRLPOOL_CLIENT_SECRET
  WHIRLPOOL_TOKEN_URL (optional)
  WHIRLPOOL_GENERATE_CONTENT_URL (optional)
  WHIRLPOOL_RUN_MODEL_LAYER=1 to exercise layer 4 (needs Django/agents on PYTHONPATH)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

import requests

DEFAULT_TOKEN_URL = "https://api-dev.whirlpool.com/oauth2/v1/token"
DEFAULT_GENERATE_URL = "https://api-dev.whirlpool.com/d2c/cxplatform/v1/ai/generateContent"


def get_token(client_id: str, client_secret: str, token_url: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        token_url,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    print("LAYER 1 token status:", response.status_code)
    response.raise_for_status()
    payload = response.json()
    token = payload["access_token"]
    print("LAYER 1 OK expires_in=", payload.get("expires_in"))
    return token


def generate_content(token: str, url: str, payload: dict) -> dict:
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    print("generateContent status:", response.status_code)
    try:
        body = response.json()
    except Exception:
        print(response.text)
        response.raise_for_status()
        raise
    print(json.dumps(body, ensure_ascii=False, indent=2)[:4000])
    response.raise_for_status()
    return body


def layer_plain_text(token: str, url: str) -> dict:
    print("\n=== LAYER 2 plain generateContent ===")
    return generate_content(
        token,
        url,
        {"contents": [{"role": "user", "parts": [{"text": "Reply with a short hello"}]}]},
    )


def layer_tools_probe(token: str, url: str) -> dict | None:
    print("\n=== LAYER 3 tools / functionDeclarations probe ===")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Call lookup_order for order 42"}]}],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "lookup_order",
                        "description": "Lookup an order by id",
                        "parameters": {
                            "type": "object",
                            "properties": {"order_id": {"type": "string"}},
                            "required": ["order_id"],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
    }
    try:
        return generate_content(token, url, payload)
    except requests.HTTPError as exc:
        print("LAYER 3 FAILED (tool calling likely unsupported):", exc)
        return None


async def layer_whirlpool_model() -> None:
    print("\n=== LAYER 4 WhirlpoolModel.get_response ===")
    from agents.model_settings import ModelSettings
    from agents.models.interface import ModelTracing

    from inline_agents.backends.openai.custom_providers.whirlpool.model import WhirlpoolModel

    model = WhirlpoolModel(
        model="custom/whirlpool/generateContent",
        credentials={
            "client_id": os.environ["WHIRLPOOL_CLIENT_ID"],
            "client_secret": os.environ["WHIRLPOOL_CLIENT_SECRET"],
            "token_url": os.getenv("WHIRLPOOL_TOKEN_URL", DEFAULT_TOKEN_URL),
            "generate_content_url": os.getenv("WHIRLPOOL_GENERATE_CONTENT_URL", DEFAULT_GENERATE_URL),
        },
    )
    response = await model.get_response(
        system_instructions="You are a concise assistant.",
        input="Say hello in one short sentence.",
        model_settings=ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=ModelTracing.DISABLED,
    )
    print("LAYER 4 OK output items:", len(response.output))
    print(response.output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Whirlpool PoC smoke test")
    parser.add_argument("--skip-tools", action="store_true", help="Skip layer 3 tools probe")
    parser.add_argument(
        "--run-model",
        action="store_true",
        help="Run layer 4 via WhirlpoolModel (or set WHIRLPOOL_RUN_MODEL_LAYER=1)",
    )
    args = parser.parse_args()

    client_id = os.getenv("WHIRLPOOL_CLIENT_ID")
    client_secret = os.getenv("WHIRLPOOL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set WHIRLPOOL_CLIENT_ID and WHIRLPOOL_CLIENT_SECRET", file=sys.stderr)
        return 1

    token_url = os.getenv("WHIRLPOOL_TOKEN_URL", DEFAULT_TOKEN_URL)
    generate_url = os.getenv("WHIRLPOOL_GENERATE_CONTENT_URL", DEFAULT_GENERATE_URL)

    token = get_token(client_id, client_secret, token_url)
    layer_plain_text(token, generate_url)

    if not args.skip_tools:
        layer_tools_probe(token, generate_url)

    run_model = args.run_model or os.getenv("WHIRLPOOL_RUN_MODEL_LAYER") == "1"
    if run_model:
        asyncio.run(layer_whirlpool_model())

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

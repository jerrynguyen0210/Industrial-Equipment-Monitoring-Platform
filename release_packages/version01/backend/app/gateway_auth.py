"""Explicit prototype bearer credentials; no caller-supplied ID grants access."""

import hmac
import json
import os
import re

from fastapi import HTTPException, Request


def load_gateway_credentials() -> dict[str, str]:
    """Map registered gateway IDs to unique tokens, failing without secret output."""

    def unique_pairs(pairs: list[tuple[str, str]]) -> dict[str, str]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        credentials = json.loads(
            os.environ.get("GATEWAY_CREDENTIALS_JSON") or "{}",
            object_pairs_hook=unique_pairs,
        )
        if not isinstance(credentials, dict):
            raise ValueError
        for gateway_id, token in credentials.items():
            if not (
                isinstance(gateway_id, str)
                and 1 <= len(gateway_id) <= 128
                and "\x00" not in gateway_id
                and isinstance(token, str)
                and re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", token)
                and not token.startswith("replace-with-")
            ):
                raise ValueError
        if len(set(credentials.values())) != len(credentials):
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        raise RuntimeError(
            "GATEWAY_CREDENTIALS_JSON must map gateway IDs to unique bearer tokens"
        ) from None
    return credentials


def resolve_gateway(request: Request) -> str:
    """Authenticate before reading the body; registry eligibility is transactional."""
    headers = request.headers.getlist("authorization")
    parts = headers[0].split() if len(headers) == 1 else []
    if len(parts) == 2 and parts[0].lower() == "bearer":
        supplied = parts[1].encode("utf-8")
        for gateway_id, token in request.app.state.gateway_credentials.items():
            if hmac.compare_digest(supplied, token.encode("ascii")):
                return gateway_id
    raise HTTPException(
        status_code=401,
        detail={
            "reason": "invalid_gateway_credential",
            "message": "Invalid credential.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

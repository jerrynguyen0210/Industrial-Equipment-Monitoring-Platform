"""Send a repeatable API-only fixture without changing event identities or numbers."""

import argparse
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials belong only to the explicitly configured target.
        return None


def classify_response(events: list, response: dict) -> list[str]:
    """Require complete ordered confirmations before reporting any item confirmed."""
    if not isinstance(response, dict):
        raise ValueError("Malformed batch response")
    results = response.get("results")
    if (
        not isinstance(response.get("batch_id"), str)
        or not response["batch_id"]
        or not isinstance(results, list)
        or len(results) != len(events)
    ):
        raise ValueError("Incomplete batch response")
    outcomes = []
    for source, result in zip(events, results, strict=True):
        if not isinstance(result, dict):
            raise ValueError("Malformed item response")
        for field in ("device_id", "boot_id", "sequence_number"):
            if (
                field not in result
                or result[field] != source.get(field)
                or type(result[field]) is not type(source.get(field))
            ):
                raise ValueError("Response identity/order mismatch")
        outcome = result.get("outcome")
        reason = result.get("reason")
        if outcome not in ("accepted", "duplicate", "rejected"):
            raise ValueError("Unknown item outcome")
        if outcome == "rejected":
            if not isinstance(reason, str) or not reason:
                raise ValueError("Rejection missing a reason")
            outcome += ":" + reason
        elif reason is not None:
            raise ValueError("Contradictory item response")
        outcomes.append(outcome)
    return outcomes


def validate_target(base_url: str, token: str) -> None:
    parsed_url = urlsplit(base_url)
    if (
        parsed_url.scheme not in ("http", "https")
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ValueError(
            "API_BASE_URL must be an HTTP(S) URL without credentials/query"
        )
    # Accessing port also rejects malformed/out-of-range ports before sending.
    try:
        _ = parsed_url.port
    except ValueError:
        raise ValueError("API_BASE_URL must have a valid port") from None
    if not token or token.startswith("replace-with-"):
        raise ValueError("Set GATEWAY_API_KEY to a provisioned test credential")


def post_batch(
    base_url: str, token: str, body: bytes, events: list, timeout: float = 30
) -> tuple[dict, list[str]]:
    """Send once, preserving bytes and requiring ordered per-item confirmations."""
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/telemetry/batches",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as reply:
        response = json.load(reply)
    return response, classify_response(events, response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument(
        "--expect", help="Exact ordered outcomes, e.g. accepted,rejected:invalid_unit"
    )
    args = parser.parse_args()
    base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api")
    token = os.environ.get("GATEWAY_API_KEY", "")
    try:
        validate_target(base_url, token)
    except ValueError as error:
        parser.error(str(error))
    try:
        body = args.batch.read_bytes()
        # Inspect shape only. Send the original bytes to retain decimal precision.
        payload = json.loads(body)
        events = payload["events"]
        if not isinstance(events, list) or not 1 <= len(events) <= 500:
            raise ValueError
        if not all(isinstance(item, dict) for item in events):
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("Fixture must contain 1 to 500 event objects in a JSON batch")
    started = time.monotonic()
    try:
        response, outcomes = post_batch(base_url, token, body, events)
    except (
        urllib.error.URLError,
        http.client.HTTPException,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ):
        print(
            json.dumps(
                {
                    "mode": "api-only",
                    "unconfirmed": len(events),
                    "error": "HTTP/response failure; keep fixture unchanged for retry",
                }
            )
        )
        raise SystemExit(1) from None
    counts = Counter(outcome.split(":", 1)[0] for outcome in outcomes)
    elapsed = time.monotonic() - started
    print(
        json.dumps(
            {
                "mode": "api-only",
                "fixture": str(args.batch),
                "batch_id": response["batch_id"],
                "outcomes": outcomes,
                "counts": dict(counts),
                "unconfirmed": 0,
                "duration_seconds": round(elapsed, 3),
            }
        )
    )
    if args.expect is not None:
        success = outcomes == args.expect.split(",")
    else:
        success = not counts["rejected"]
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()

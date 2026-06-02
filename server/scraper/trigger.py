"""
Webhook trigger for Hermes Agent scraping requests.
Sends signed POST to Hermes webhook endpoint.
"""

import hashlib
import hmac
import json
import urllib.request

from shared.config import WEBHOOK_URL, WEBHOOK_SECRET


def trigger_scraping(symbol: str) -> bool:
    """Send a webhook to Hermes to trigger company data scraping.
    Returns True if webhook was accepted (202), False otherwise."""
    body = json.dumps({
        "symbol": symbol,
        "action": "scrape_company"
    }).encode("utf-8")

    sig = hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}"
        },
        method="POST"
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        resp_body = resp.read().decode(errors='replace')
        if status == 202:
            print(f"[scraper] Webhook ACCEPTED for {symbol}: {resp_body}", flush=True)
        else:
            print(f"[scraper] Webhook unexpected status for {symbol}: HTTP {status} — {resp_body[:200]}", flush=True)
        return status == 202
    except urllib.error.HTTPError as e:
        print(f"[scraper] Webhook failed for {symbol}: HTTP {e.code} — {e.read().decode(errors='replace')[:200]}", flush=True)
        return False
    except Exception as e:
        print(f"[scraper] Webhook error for {symbol}: {e}", flush=True)
        return False

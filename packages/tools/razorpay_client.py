"""
packages/tools/razorpay_client.py
Razorpay API client for AI Squadron — subscriptions, payments, webhooks.

Setup (Railway environment variables):
  RAZORPAY_KEY_ID     — starts with rzp_test_ (sandbox) or rzp_live_ (production)
  RAZORPAY_KEY_SECRET — the paired secret from the Razorpay dashboard
  RAZORPAY_WEBHOOK_SECRET — set in Razorpay Dashboard → Webhooks → Add webhook secret

How to get credentials:
  1. dashboard.razorpay.com → Settings → API Keys → Generate Test Keys
  2. For international payments (USD from non-Indian customers):
     Settings → International Payments → submit GST cert + business docs

Settlement note (India):
  RBI requires all Indian businesses to receive settlement in INR regardless of
  the customer's payment currency. Razorpay charges customers in USD, converts
  at the prevailing market rate (~RBI reference rate), and deposits INR to your
  Indian bank account. This is not a Razorpay limitation — it applies to ALL
  Indian payment aggregators by law.

Subscription flow:
  1. Backend: create_subscription(plan_id) → subscription_id
  2. Frontend: open Razorpay checkout with subscription_id
  3. Customer pays → Razorpay calls your webhook
  4. Backend: verify_payment_signature() → update user_subscriptions table
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Plan IDs created in the Razorpay dashboard (or via create_plan).
# These are stable — create them once and store the IDs in env vars.
PLAN_ENV_MAP: dict[str, str] = {
    "builder_monthly":  "RAZORPAY_PLAN_BUILDER_MONTHLY",
    "builder_annual":   "RAZORPAY_PLAN_BUILDER_ANNUAL",
    "studio_monthly":   "RAZORPAY_PLAN_STUDIO_MONTHLY",
    "studio_annual":    "RAZORPAY_PLAN_STUDIO_ANNUAL",
}


def razorpay_available() -> bool:
    key_id     = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    return bool(key_id and key_secret and len(key_id) > 10 and len(key_secret) > 10)


def _get_client():
    """Return an authenticated razorpay.Client instance."""
    try:
        import razorpay  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "razorpay package not installed. Run: pip install razorpay"
        ) from exc

    key_id     = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise EnvironmentError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in Railway env vars.\n"
            "Get them from: dashboard.razorpay.com → Settings → API Keys"
        )
    return razorpay.Client(auth=(key_id, key_secret))


# ─── Plans ────────────────────────────────────────────────────────────────────

def create_plan(name: str, amount_usd_cents: int, interval: str = "monthly") -> str:
    """
    Create a Razorpay subscription plan. Call this once per plan during initial setup.
    Stores the returned plan_id as RAZORPAY_PLAN_* env var.

    Args:
        name: human-readable plan name (e.g. "Builder Monthly")
        amount_usd_cents: price in USD cents (e.g. $49 = 4900)
        interval: "monthly" or "yearly"

    Returns: plan_id (e.g. "plan_XXXXXXXXXX")
    """
    client = _get_client()
    period = "yearly" if interval == "yearly" else "monthly"
    plan = client.plan.create({
        "period":   period,
        "interval": 1,
        "item": {
            "name":        name,
            "amount":      amount_usd_cents,
            "currency":    "USD",
            "description": name,
        },
        "notes": {"source": "ai-squadron"},
    })
    log.info("[RAZORPAY] Created plan: %s → %s", name, plan["id"])
    return plan["id"]


def get_plan_id(plan_key: str) -> str:
    """
    Return the Razorpay plan_id for a given plan key.
    plan_key: one of 'builder_monthly', 'builder_annual', 'studio_monthly', 'studio_annual'
    """
    env_var = PLAN_ENV_MAP.get(plan_key)
    if not env_var:
        raise ValueError(f"Unknown plan key: {plan_key}")
    plan_id = os.getenv(env_var, "")
    if not plan_id:
        raise EnvironmentError(
            f"{env_var} not set. Create the plan in Razorpay dashboard first:\n"
            f"  from packages.tools.razorpay_client import create_plan\n"
            f"  create_plan('Builder Monthly', 4900, 'monthly')"
        )
    return plan_id


# ─── Subscriptions ────────────────────────────────────────────────────────────

def create_subscription(
    plan_key: str,
    user_id: str,
    user_email: str,
    total_billing_cycles: int = 120,
) -> dict[str, str]:
    """
    Create a Razorpay subscription for a user.

    Returns dict with:
      subscription_id: str   — pass to Razorpay checkout on the frontend
      plan_id: str
      status: str            — "created"

    The frontend opens Razorpay checkout with this subscription_id.
    After payment, the webhook fires and we mark the subscription active.
    """
    plan_id = get_plan_id(plan_key)
    client  = _get_client()

    sub = client.subscription.create({
        "plan_id":          plan_id,
        "customer_notify":  1,    # Razorpay emails the customer on renewal
        "quantity":         1,
        "total_count":      total_billing_cycles,
        "notes": {
            "user_id":    user_id,
            "user_email": user_email,
            "plan_key":   plan_key,
            "source":     "ai-squadron",
        },
    })

    log.info("[RAZORPAY] Created subscription %s for user=%s plan=%s",
             sub["id"], user_id[:8], plan_key)
    return {
        "subscription_id": sub["id"],
        "plan_id":         plan_id,
        "status":          sub.get("status", "created"),
    }


def fetch_subscription(subscription_id: str) -> dict[str, Any]:
    """Fetch a subscription's current status from Razorpay."""
    client = _get_client()
    return client.subscription.fetch(subscription_id)


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: bool = True) -> dict:
    """
    Cancel a subscription.
    cancel_at_cycle_end=True: customer keeps access until billing period ends.
    cancel_at_cycle_end=False: immediate cancellation.
    """
    client = _get_client()
    return client.subscription.cancel(subscription_id, {
        "cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0,
    })


# ─── Signature verification ───────────────────────────────────────────────────

def verify_payment_signature(
    razorpay_payment_id: str,
    razorpay_subscription_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature returned by Razorpay checkout.

    The frontend receives razorpay_payment_id, razorpay_subscription_id, and
    razorpay_signature after the user completes payment. POST these to the backend
    and call this function before marking the subscription as active.

    Returns True if the signature is valid (payment is genuine).
    """
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not key_secret:
        raise EnvironmentError("RAZORPAY_KEY_SECRET not set")

    message = f"{razorpay_payment_id}|{razorpay_subscription_id}"
    expected = hmac.new(
        key_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, razorpay_signature)


def verify_webhook_signature(body: bytes, razorpay_signature: str) -> bool:
    """
    Verify a Razorpay webhook request using the webhook secret.

    Razorpay includes 'X-Razorpay-Signature' header with each webhook.
    The signature is HMAC-SHA256 of the raw request body using the webhook secret.

    Set RAZORPAY_WEBHOOK_SECRET in Razorpay Dashboard → Webhooks → Add webhook.
    Point the webhook to: https://your-app.up.railway.app/api/webhooks/razorpay
    Events to subscribe: subscription.charged, subscription.cancelled, payment.failed
    """
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        log.warning("[RAZORPAY] RAZORPAY_WEBHOOK_SECRET not set — skipping signature check")
        return True  # permit but log — don't hard-fail before secret is configured

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, razorpay_signature)


# ─── Plan setup helper ────────────────────────────────────────────────────────

def setup_plans() -> dict[str, str]:
    """
    One-time helper: create all four subscription plans in Razorpay and print
    the plan IDs to add as Railway environment variables.

    Run once after connecting your Razorpay account:
      python -c "from packages.tools.razorpay_client import setup_plans; setup_plans()"
    """
    plans = {
        "builder_monthly": ("Builder Monthly", 4900),    # $49/mo
        "builder_annual":  ("Builder Annual",  46800),   # $468/yr ($39/mo equivalent)
        "studio_monthly":  ("Studio Monthly",  14900),   # $149/mo
        "studio_annual":   ("Studio Annual",   142800),  # $1,428/yr ($119/mo equivalent)
    }

    created: dict[str, str] = {}
    for key, (name, amount_cents) in plans.items():
        env_var = PLAN_ENV_MAP[key]
        existing = os.getenv(env_var, "")
        if existing:
            log.info("[RAZORPAY] Plan %s already set: %s", key, existing)
            created[key] = existing
            continue

        interval = "yearly" if "annual" in key else "monthly"
        plan_id = create_plan(name, amount_cents, interval)
        created[key] = plan_id
        print(f"Add to Railway env vars:  {env_var}={plan_id}")

    return created

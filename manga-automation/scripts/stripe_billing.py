"""
Stripe billing integration for AiToEarn SaaS.

Endpoints (registered in worker.py):
    POST /billing/create-checkout  — create Stripe Checkout session for a plan
    POST /billing/webhook          — receive Stripe webhook events
    GET  /billing/subscription-status — query current plan for an organization

Requires: STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET
in environment.
"""

import json
import os
import stripe
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# ── Plan definitions ──────────────────────────────────────────────────────────
PLANS = {
    "hobbyist": {
        "name": "Hobbyist",
        "price_id": "price_hobbyist_monthly",
        "amount": 2900,
        "currency": "usd",
        "interval": "month",
        "features": ["1 TikTok account", "12 videos/week", "Basic analytics"],
    },
    "pro": {
        "name": "Pro",
        "price_id": "price_pro_monthly",
        "amount": 9900,
        "currency": "usd",
        "interval": "month",
        "features": [
            "5 TikTok accounts",
            "60 videos/week",
            "Advanced analytics",
            "Proxy support",
            "Engagement automation",
        ],
    },
    "agency": {
        "name": "Agency",
        "price_id": "price_agency_monthly",
        "amount": 29900,
        "currency": "usd",
        "interval": "month",
        "features": [
            "Unlimited TikTok accounts",
            "Unlimited videos",
            "All features",
            "Priority support",
            "Multi-platform publishing",
            "White-label dashboard",
        ],
    },
}


def _db():
    """Return a database connection from the shared utilities."""
    from scripts.utils.database import get_connection

    return get_connection()


# ── Checkout ──────────────────────────────────────────────────────────────────


def create_checkout_session(
    plan_tier: str,
    organization_id: int,
    customer_email: str | None = None,
    success_url: str = "http://localhost:3000/dashboard?checkout=success",
    cancel_url: str = "http://localhost:3000/dashboard?checkout=canceled",
) -> dict:
    """Create a Stripe Checkout session and return the URL.

    The caller redirects the user to session_url so Stripe handles the payment page.
    When checkout completes, Stripe fires a webhook that updates our database.
    """
    price_id = PLANS[plan_tier]["price_id"]

    # Look up or create the Stripe Customer
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "SELECT stripe_customer_id FROM organizations WHERE id = %s",
        (organization_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Organization {organization_id} not found")

    customer_id = row[0] if row else None

    if customer_id:
        stripe_customer = stripe.Customer.retrieve(customer_id)
    else:
        stripe_customer = stripe.Customer.create(
            email=customer_email or "",
            metadata={"organization_id": str(organization_id)},
        )
        cur.execute(
            "UPDATE organizations SET stripe_customer_id = %s WHERE id = %s",
            (stripe_customer.id, organization_id),
        )
        conn.commit()

    session = stripe.checkout.Session.create(
        customer=stripe_customer.id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"organization_id": str(organization_id), "plan_tier": plan_tier},
        subscription_data={
            "metadata": {
                "organization_id": str(organization_id),
                "plan_tier": plan_tier,
            }
        },
    )
    conn.close()

    return {
        "session_id": session.id,
        "session_url": session.url,
        "plan_tier": plan_tier,
        "organization_id": organization_id,
    }


# ── Customer Portal ───────────────────────────────────────────────────────────


def create_customer_portal_session(
    organization_id: int,
    return_url: str = "http://localhost:3000/dashboard",
) -> dict:
    """Create a Stripe Customer Portal session for self-serve billing management."""
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "SELECT stripe_customer_id FROM organizations WHERE id = %s",
        (organization_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        raise ValueError(f"No Stripe customer for organization {organization_id}")

    session = stripe.billing_portal.Session.create(
        customer=row[0],
        return_url=return_url,
    )
    return {"portal_url": session.url, "organization_id": organization_id}


# ── Webhook ───────────────────────────────────────────────────────────────────


def handle_webhook(payload: bytes, signature: str) -> dict:
    """Verify Stripe webhook signature, process the event, update subscription state.

    Returns a dict with event_type, status, and action taken.
    """
    if not WEBHOOK_SECRET:
        return {"error": "STRIPE_WEBHOOK_SECRET not configured"}

    try:
        event = stripe.Webhook.construct_event(payload, signature, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid webhook signature"}

    event_type = event["type"]
    data = event["data"]["object"]
    subscription_id = data.get("id", "")
    customer_id = data.get("customer", "")

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data)

    elif event_type == "customer.subscription.created":
        return _handle_subscription_created(data)

    elif event_type == "customer.subscription.updated":
        return _handle_subscription_updated(data)

    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(data)

    elif event_type == "invoice.paid":
        return {"status": "ok", "action": "invoice_paid", "subscription_id": subscription_id}

    return {
        "status": "ok",
        "action": "ignored",
        "event_type": event_type,
    }


def _handle_checkout_completed(session: dict) -> dict:
    subscription_id = session.get("subscription", "")
    customer_id = session.get("customer", "")
    metadata = session.get("metadata", {})
    organization_id = int(metadata.get("organization_id", 0))
    plan_tier = metadata.get("plan_tier", "hobbyist")

    if not organization_id or not subscription_id:
        return {"status": "ok", "action": "checkout_no_org", "reason": "missing metadata"}

    _upsert_subscription(organization_id, customer_id, subscription_id, plan_tier, "active")

    return {
        "status": "ok",
        "action": "checkout_completed",
        "organization_id": organization_id,
        "plan_tier": plan_tier,
    }


def _handle_subscription_created(subscription: dict) -> dict:
    return _sync_subscription_from_stripe(subscription, "created")


def _handle_subscription_updated(subscription: dict) -> dict:
    return _sync_subscription_from_stripe(subscription, "updated")


def _handle_subscription_deleted(subscription: dict) -> dict:
    return _sync_subscription_from_stripe(subscription, "deleted")


def _sync_subscription_from_stripe(subscription: dict, action: str) -> dict:
    subscription_id = subscription.get("id", "")
    customer_id = subscription.get("customer", "")
    status = subscription.get("status", "inactive")
    metadata = subscription.get("metadata", {})
    organization_id = int(metadata.get("organization_id", 0))
    plan_tier = metadata.get("plan_tier", "hobbyist")
    price_id = subscription.get("items", {}).get("data", [{}])[0].get("price", {}).get("id", "")
    current_period_end = subscription.get("current_period_end")

    if current_period_end:
        current_period_end = datetime.fromtimestamp(current_period_end)

    if not organization_id:
        return {"status": "ok", "action": f"subscription_{action}", "note": "no organization_id in metadata"}

    _upsert_subscription(
        organization_id, customer_id, subscription_id, plan_tier, status, price_id, current_period_end
    )

    return {
        "status": "ok",
        "action": f"subscription_{action}",
        "organization_id": organization_id,
        "stripe_status": status,
    }


def _upsert_subscription(
    organization_id: int,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    plan_tier: str,
    status: str,
    price_id: str = "",
    current_period_end: datetime | None = None,
) -> None:
    conn = _db()
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO subscriptions
              (organization_id, stripe_customer_id, stripe_subscription_id,
               price_id, plan_tier, status, current_period_end)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (stripe_subscription_id)
           DO UPDATE SET plan_tier = EXCLUDED.plan_tier,
                         status = EXCLUDED.status,
                         price_id = EXCLUDED.price_id,
                         current_period_end = EXCLUDED.current_period_end,
                         updated_at = NOW()""",
        (
            organization_id,
            stripe_customer_id,
            stripe_subscription_id,
            price_id,
            plan_tier,
            status,
            current_period_end,
        ),
    )
    conn.commit()
    conn.close()


# ── Status queries ────────────────────────────────────────────────────────────


def get_subscription_status(organization_id: int) -> dict:
    """Return the current subscription state for an organization."""
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """SELECT plan_tier, status, current_period_end, stripe_subscription_id
           FROM subscriptions
           WHERE organization_id = %s
           ORDER BY created_at DESC
           LIMIT 1""",
        (organization_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "organization_id": organization_id,
            "subscribed": False,
            "plan_tier": None,
        }

    return {
        "organization_id": organization_id,
        "subscribed": row[1] in ("active", "trialing"),
        "plan_tier": row[0],
        "status": row[1],
        "current_period_end": row[2].isoformat() if row[2] else None,
        "stripe_subscription_id": row[3],
    }


def list_plans() -> list[dict]:
    """Return available plans with public info (no price IDs)."""
    return [
        {
            "tier": key,
            "name": p["name"],
            "amount": p["amount"],
            "currency": p["currency"],
            "interval": p["interval"],
            "features": p["features"],
        }
        for key, p in PLANS.items()
    ]

"""
Seed the outreach tables with initial demo data.
Run: python -m scripts.seed_outreach
"""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.cjlfvbqztjqveuneglfn:t4iZF5UgmJ3Rpb2t@aws-1-us-east-1.pooler.supabase.com:5432/postgres",
)
# Convert to async driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

LLOYD_USER_ID = "9baf8117-db65-4f30-87a5-a76cf4f23d82"

# ── Data ──────────────────────────────────────────────────────────────────

SENDERS = [
    {"name": "Santi", "total_accounts": 10, "send_per_account": 50, "days_per_webinar": 5, "color": "violet", "display_order": 0},
    {"name": "Skarpe", "total_accounts": 8, "send_per_account": 50, "days_per_webinar": 5, "color": "blue", "display_order": 1},
    {"name": "Lina", "total_accounts": 6, "send_per_account": 50, "days_per_webinar": 5, "color": "emerald", "display_order": 2},
]

BUCKETS = [
    {"name": "Accounting, Audit & Tax Services", "industry": "Accounting", "total_contacts": 38400, "remaining_contacts": 32100, "countries": ["US", "UK", "CA"], "emp_range": "5-50"},
    {"name": "Financial Planning & Advisory", "industry": "Financial Planning", "total_contacts": 22100, "remaining_contacts": 19800, "countries": ["US", "AU"], "emp_range": "5-50"},
    {"name": "Insurance Brokerage", "industry": "Insurance", "total_contacts": 8900, "remaining_contacts": 7200, "countries": ["US"], "emp_range": "5-50"},
    {"name": "Professional Training & Coaching", "industry": "Pro Training", "total_contacts": 15200, "remaining_contacts": 13400, "countries": ["US"], "emp_range": "0-10"},
    {"name": "Wealth Management", "industry": "Wealth Mgmt", "total_contacts": 11200, "remaining_contacts": 9400, "countries": ["US", "UK"], "emp_range": "10-50"},
    {"name": "Real Estate Services", "industry": "Real Estate", "total_contacts": 6300, "remaining_contacts": 5100, "countries": ["US"], "emp_range": "5-50"},
    {"name": "Legal Services", "industry": "Legal", "total_contacts": 4200, "remaining_contacts": 3800, "countries": ["US", "UK", "CA"], "emp_range": "5-25"},
    {"name": "Business Consulting", "industry": "Consulting", "total_contacts": 3100, "remaining_contacts": 2900, "countries": ["US"], "emp_range": "1-25"},
    {"name": "IT Services & MSP", "industry": "IT Services", "total_contacts": 2400, "remaining_contacts": 2100, "countries": ["US", "IN"], "emp_range": "5-50"},
    {"name": "Marketing & Advertising Agency", "industry": "Marketing", "total_contacts": 2200, "remaining_contacts": 1900, "countries": ["US", "UK"], "emp_range": "1-25"},
]

WEBINARS = [
    {"number": 133, "date": "2026-03-31", "status": "sent", "broadcast_id": "6012344", "main_title": "TITLE: Revealed: How Professional Service Firms Using AI Powered Webinars..."},
    {"number": 134, "date": "2026-04-07", "status": "sent", "broadcast_id": "6047654", "main_title": "TITLE: Revealed: How Professional Service Firms Using AI Powered Webinars..."},
    {"number": 135, "date": "2026-04-14", "status": "planning"},
]


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            # Ensure user exists
            result = await session.execute(
                text("SELECT id FROM users WHERE id = :uid"),
                {"uid": LLOYD_USER_ID},
            )
            if not result.scalar_one_or_none():
                await session.execute(
                    text("INSERT INTO users (id) VALUES (:uid)"),
                    {"uid": LLOYD_USER_ID},
                )
                print(f"✓ Created user {LLOYD_USER_ID}")

            # ── Senders ──────────────────────────────────────────
            existing_senders = await session.execute(
                text("SELECT id FROM outreach_senders WHERE user_id = :uid"),
                {"uid": LLOYD_USER_ID},
            )
            if existing_senders.first():
                print("⏭ Senders already exist, skipping...")
            else:
                for s in SENDERS:
                    await session.execute(
                        text("""
                            INSERT INTO outreach_senders (id, user_id, name, total_accounts, send_per_account, days_per_webinar, color, display_order, is_active)
                            VALUES (gen_random_uuid(), :uid, :name, :accts, :spa, :dpw, :color, :order, true)
                        """),
                        {"uid": LLOYD_USER_ID, "name": s["name"], "accts": s["total_accounts"], "spa": s["send_per_account"], "dpw": s["days_per_webinar"], "color": s["color"], "order": s["display_order"]},
                    )
                print(f"✓ Inserted {len(SENDERS)} senders")

            # ── Buckets ──────────────────────────────────────────
            existing_buckets = await session.execute(
                text("SELECT id FROM outreach_buckets WHERE user_id = :uid AND deleted_at IS NULL"),
                {"uid": LLOYD_USER_ID},
            )
            if existing_buckets.first():
                print("⏭ Buckets already exist, skipping...")
            else:
                for b in BUCKETS:
                    await session.execute(
                        text("""
                            INSERT INTO outreach_buckets (id, user_id, name, industry, total_contacts, remaining_contacts, countries, emp_range)
                            VALUES (gen_random_uuid(), :uid, :name, :industry, :total, :remaining, :countries, :emp)
                        """),
                        {"uid": LLOYD_USER_ID, "name": b["name"], "industry": b["industry"], "total": b["total_contacts"], "remaining": b["remaining_contacts"], "countries": b["countries"], "emp": b["emp_range"]},
                    )
                print(f"✓ Inserted {len(BUCKETS)} buckets")

            # ── Webinars ─────────────────────────────────────────
            existing_webinars = await session.execute(
                text("SELECT id FROM webinars WHERE user_id = :uid"),
                {"uid": LLOYD_USER_ID},
            )
            if existing_webinars.first():
                print("⏭ Webinars already exist, skipping...")
            else:
                for w in WEBINARS:
                    await session.execute(
                        text("""
                            INSERT INTO webinars (id, user_id, number, date, status, broadcast_id, main_title)
                            VALUES (gen_random_uuid(), :uid, :num, :date, :status, :bid, :title)
                        """),
                        {
                            "uid": LLOYD_USER_ID,
                            "num": w["number"],
                            "date": w["date"],
                            "status": w["status"],
                            "bid": w.get("broadcast_id"),
                            "title": w.get("main_title"),
                        },
                    )
                print(f"✓ Inserted {len(WEBINARS)} webinars")

        print("\n🎉 Seed complete!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

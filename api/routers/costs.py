"""Cost tracking endpoint — returns API usage and cost summary for the build dashboard."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from db.session import get_db

router = APIRouter(prefix="/api", tags=["costs"])


@router.get("/costs")
async def get_costs(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    today_usd = await db.scalar(text(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM api_cost_log WHERE created_at >= CURRENT_DATE"
    ))
    week_usd = await db.scalar(text(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM api_cost_log WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"
    ))
    daily_rows = (await db.execute(text("""
        SELECT DATE(created_at AT TIME ZONE 'UTC') as date, COALESCE(SUM(cost_usd), 0) as cost_usd
        FROM api_cost_log
        WHERE created_at >= CURRENT_DATE - make_interval(days => :days)
        GROUP BY DATE(created_at AT TIME ZONE 'UTC') ORDER BY date
    """), {"days": days})).fetchall()
    by_api_rows = (await db.execute(text("""
        SELECT api_name, model, COALESCE(SUM(cost_usd), 0) as cost_usd, COUNT(*) as calls
        FROM api_cost_log
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY api_name, model ORDER BY cost_usd DESC
    """))).fetchall()
    session_rows = (await db.execute(text("""
        SELECT session_id, session_label, COALESCE(SUM(cost_usd), 0) as cost_usd, MAX(created_at) as ts
        FROM api_cost_log
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days' AND session_id IS NOT NULL
        GROUP BY session_id, session_label ORDER BY ts DESC LIMIT 20
    """))).fetchall()

    return {
        "summary": {"today_usd": float(today_usd or 0), "week_usd": float(week_usd or 0)},
        "daily": [{"date": str(r.date), "cost_usd": float(r.cost_usd)} for r in daily_rows],
        "by_api": [
            {"api": f"{r.api_name}/{r.model}" if r.model else r.api_name,
             "cost_usd": float(r.cost_usd), "calls": r.calls}
            for r in by_api_rows
        ],
        "sessions": [
            {"session_id": r.session_id, "label": r.session_label or r.session_id,
             "cost_usd": float(r.cost_usd), "timestamp": r.ts.isoformat()}
            for r in session_rows
        ],
    }

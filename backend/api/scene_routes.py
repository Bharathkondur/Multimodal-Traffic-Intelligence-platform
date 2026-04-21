"""
REST endpoints for Scene Intelligence: watchlist rules, monitor zones,
and alert history.

These routes share state with the StreamProcessor via a process-local
``MonitorEngine`` (kept on ``app.state.monitor_engine``). Persistence
happens lazily — when a rule/zone is created via this API we both push
it into the engine (so it takes effect immediately) and write a row
to the DB so it survives a restart.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from config import settings
from database.connection import AsyncSessionFactory
from database.models import Alert, MonitorZone, WatchRule
from processing.monitors import (
    DEMO_RULES,
    MonitorEngine,
    Rule,
    seed_demo_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{settings.api_prefix}/scene", tags=["scene-intel"])


# ---------------------------------------------------------------------------
# Pydantic schemas (kept inline because they're tiny and one-use)
# ---------------------------------------------------------------------------


class RuleCreate(BaseModel):
    text: str = Field(..., description="English rule text — see /docs/rules.md")
    name: Optional[str] = None
    severity: str = Field("info", pattern="^(info|warning|critical)$")
    cooldown_s: float = 15.0


class RuleOut(BaseModel):
    id: str
    name: str
    raw_text: str
    enabled: bool
    severity: str
    cooldown_s: float
    predicate: dict | None = None


class ZoneIn(BaseModel):
    id: str
    name: str
    points: list[list[float]]
    color: Optional[str] = None


class ZoneOut(ZoneIn):
    pass


class AlertOut(BaseModel):
    id: str
    rule_id: Optional[str]
    rule_name: str
    severity: str
    reason: Optional[str]
    zone_id: Optional[str]
    frame_id: Optional[int]
    timestamp: datetime
    matched_objects: list | None = None
    has_snapshot: bool = False


# ---------------------------------------------------------------------------
# Engine accessor — initialised lazily on app.state
# ---------------------------------------------------------------------------


def _engine(request: Request) -> MonitorEngine:
    eng = getattr(request.app.state, "monitor_engine", None)
    if eng is None:
        eng = MonitorEngine()
        request.app.state.monitor_engine = eng
    return eng


def _db() -> AsyncSessionFactory:
    return AsyncSessionFactory(database_url=settings.get_database_url())


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/rules", response_model=List[RuleOut])
async def list_rules(session_id: str, request: Request) -> List[RuleOut]:
    rules = _engine(request).list_rules(session_id)
    return [
        RuleOut(
            id=r.id, name=r.name, raw_text=r.raw_text,
            enabled=r.enabled, severity=r.severity,
            cooldown_s=r.cooldown_s, predicate=r.predicate,
        )
        for r in rules
    ]


@router.post("/sessions/{session_id}/rules", response_model=RuleOut)
async def create_rule(
    session_id: str, body: RuleCreate, request: Request
) -> RuleOut:
    if len(_engine(request).list_rules(session_id)) >= getattr(
        settings, "max_rules_per_session", 20
    ):
        raise HTTPException(400, "Rule limit reached for this session")

    rule = Rule.from_text(session_id, body.text, name=body.name)
    rule.severity = body.severity
    rule.cooldown_s = body.cooldown_s
    _engine(request).add_rule(rule)

    # Persist
    try:
        async with _db().session_context() as db:
            db.add(WatchRule(
                id=rule.id,
                session_id=session_id,
                name=rule.name,
                raw_text=rule.raw_text,
                predicate=rule.predicate,
                enabled=rule.enabled,
                severity=rule.severity,
                cooldown_s=rule.cooldown_s,
                created_at=rule.created_at,
            ))
    except Exception as e:
        logger.warning(f"Rule persist failed (engine still active): {e}")

    return RuleOut(
        id=rule.id, name=rule.name, raw_text=rule.raw_text,
        enabled=rule.enabled, severity=rule.severity,
        cooldown_s=rule.cooldown_s, predicate=rule.predicate,
    )


@router.delete("/sessions/{session_id}/rules/{rule_id}")
async def delete_rule(
    session_id: str, rule_id: str, request: Request
) -> dict:
    removed = _engine(request).remove_rule(session_id, rule_id)
    try:
        async with _db().session_context() as db:
            from sqlalchemy import delete
            await db.execute(
                delete(WatchRule).where(WatchRule.id == rule_id)
            )
    except Exception as e:
        logger.debug(f"Rule DB delete failed: {e}")
    return {"removed": removed}


@router.post("/sessions/{session_id}/rules/seed", response_model=List[RuleOut])
async def seed_rules(session_id: str, request: Request) -> List[RuleOut]:
    """Seed the four canonical demo rules onto a session."""
    created = seed_demo_rules(_engine(request), session_id)
    try:
        async with _db().session_context() as db:
            for rule in created:
                db.add(WatchRule(
                    id=rule.id,
                    session_id=session_id,
                    name=rule.name,
                    raw_text=rule.raw_text,
                    predicate=rule.predicate,
                    enabled=rule.enabled,
                    severity=rule.severity,
                    cooldown_s=rule.cooldown_s,
                    created_at=rule.created_at,
                ))
    except Exception as e:
        logger.warning(f"Rule seed persist failed: {e}")

    return [
        RuleOut(
            id=r.id, name=r.name, raw_text=r.raw_text,
            enabled=r.enabled, severity=r.severity,
            cooldown_s=r.cooldown_s, predicate=r.predicate,
        )
        for r in created
    ]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/zones", response_model=List[ZoneOut])
async def list_zones(session_id: str, request: Request) -> List[ZoneOut]:
    return [ZoneOut(**z) for z in _engine(request).list_zones(session_id)]


@router.put("/sessions/{session_id}/zones", response_model=List[ZoneOut])
async def replace_zones(
    session_id: str, body: List[ZoneIn], request: Request
) -> List[ZoneOut]:
    """Atomic replace — UI sends the whole zone set on each save."""
    payload = [z.model_dump() for z in body]
    _engine(request).set_zones(session_id, payload)

    try:
        async with _db().session_context() as db:
            from sqlalchemy import delete as sql_delete
            await db.execute(
                sql_delete(MonitorZone).where(MonitorZone.session_id == session_id)
            )
            for z in payload:
                db.add(MonitorZone(
                    id=z["id"],
                    session_id=session_id,
                    name=z["name"],
                    points=z["points"],
                    color=z.get("color"),
                ))
    except Exception as e:
        logger.warning(f"Zone persist failed: {e}")

    return [ZoneOut(**z) for z in payload]


# ---------------------------------------------------------------------------
# Alert history
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/alerts", response_model=List[AlertOut])
async def list_alerts(
    session_id: str, limit: int = 100, severity: Optional[str] = None
) -> List[AlertOut]:
    try:
        async with _db().session_context() as db:
            stmt = (
                select(Alert)
                .where(Alert.session_id == session_id)
                .order_by(desc(Alert.timestamp))
                .limit(limit)
            )
            if severity:
                stmt = stmt.where(Alert.severity == severity)
            res = await db.execute(stmt)
            rows = res.scalars().all()
            return [
                AlertOut(
                    id=r.id,
                    rule_id=r.rule_id,
                    rule_name=r.rule_name,
                    severity=r.severity,
                    reason=r.reason,
                    zone_id=r.zone_id,
                    frame_id=r.frame_id,
                    timestamp=r.timestamp,
                    matched_objects=r.matched_objects,
                    has_snapshot=bool(r.snapshot_b64),
                )
                for r in rows
            ]
    except Exception as e:
        logger.error(f"List alerts failed: {e}")
        raise HTTPException(500, "Failed to fetch alerts")


@router.get("/sessions/{session_id}/alerts/{alert_id}/snapshot")
async def get_alert_snapshot(session_id: str, alert_id: str) -> dict:
    """Return the JPEG snapshot for an alert as a base64 data URL."""
    try:
        async with _db().session_context() as db:
            res = await db.execute(
                select(Alert).where(
                    Alert.id == alert_id, Alert.session_id == session_id
                )
            )
            row = res.scalar_one_or_none()
            if row is None or not row.snapshot_b64:
                raise HTTPException(404, "Snapshot not available")
            return {
                "alert_id": row.id,
                "data_url": f"data:image/jpeg;base64,{row.snapshot_b64}",
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Snapshot fetch failed: {e}")
        raise HTTPException(500, "Failed to fetch snapshot")


# ---------------------------------------------------------------------------
# Convenience: list demo-rule presets without instantiating them
# ---------------------------------------------------------------------------


@router.get("/rule-presets")
async def list_presets() -> list[dict]:
    return DEMO_RULES

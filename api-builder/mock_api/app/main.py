from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Workflow Test API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_BEARER_TOKEN = "demo-token"
AUTH_API_KEY = "demo-key"

USERS = [
    {"id": f"user-{i}", "name": f"User {i}", "tier": "gold" if i % 3 == 0 else "standard", "active": i % 5 != 0}
    for i in range(1, 61)
]

ORDERS = [
    {
        "id": f"ord-{i}",
        "user_id": f"user-{(i % 20) + 1}",
        "amount": round((i * 17.35) % 500 + 20, 2),
        "status": "failed" if i % 13 == 0 else ("pending" if i % 4 == 0 else "ok"),
        "created_at": datetime(2025, 1, (i % 28) + 1, tzinfo=UTC).isoformat(),
    }
    for i in range(1, 141)
]

_fail_state: dict[str, int] = {}
_fail_state_lock = Lock()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/check")
def auth_check(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    bearer_ok = authorization == f"Bearer {AUTH_BEARER_TOKEN}"
    api_key_ok = x_api_key == AUTH_API_KEY
    if not (bearer_ok or api_key_ok):
        raise HTTPException(status_code=401, detail="Invalid auth")
    return {
        "authenticated": True,
        "method": "bearer" if bearer_ok else "api_key",
        "scopes": ["read:users", "read:orders", "write:test"],
    }


@app.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    active_only: bool = Query(default=False),
    tier: str | None = Query(default=None),
) -> dict[str, Any]:
    filtered = USERS
    if active_only:
        filtered = [u for u in filtered if u["active"]]
    if tier:
        filtered = [u for u in filtered if u["tier"] == tier]

    total = len(filtered)
    offset = (page - 1) * page_size
    data = filtered[offset : offset + page_size]
    next_page = page + 1 if offset + page_size < total else None

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "next_page": next_page,
        "data": data,
    }


@app.get("/users/{user_id}")
def get_user(user_id: str) -> dict[str, Any]:
    user = next((u for u in USERS if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/orders")
def list_orders(
    status: str | None = Query(default=None),
    min_amount: float | None = Query(default=None, ge=0),
    max_amount: float | None = Query(default=None, ge=0),
    user_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    filtered = ORDERS
    if status:
        filtered = [o for o in filtered if o["status"] == status]
    if min_amount is not None:
        filtered = [o for o in filtered if o["amount"] >= min_amount]
    if max_amount is not None:
        filtered = [o for o in filtered if o["amount"] <= max_amount]
    if user_id:
        filtered = [o for o in filtered if o["user_id"] == user_id]

    total = len(filtered)
    offset = (page - 1) * page_size
    data = filtered[offset : offset + page_size]
    next_page = page + 1 if offset + page_size < total else None

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "next_page": next_page,
        "data": data,
    }


@app.post("/logic/branch")
def branch_logic(payload: dict[str, Any]) -> dict[str, Any]:
    amount = float(payload.get("amount", 0))
    retries = int(payload.get("retries", 0))
    approved = amount <= 250 and retries < 2
    reason = "within_threshold" if approved else "manual_review"
    return {
        "input": payload,
        "decision": "approve" if approved else "review",
        "approved": approved,
        "reason": reason,
    }


@app.get("/fanout/targets")
def fanout_targets(count: int = Query(default=5, ge=1, le=50)) -> dict[str, Any]:
    targets = [{"target_id": f"t-{i}", "weight": (i % 5) + 1} for i in range(1, count + 1)]
    return {"targets": targets}


@app.get("/fanout/targets/{target_id}/detail")
async def target_detail(
    target_id: str,
    delay_ms: int = Query(default=120, ge=0, le=5000),
    fail: bool = Query(default=False),
) -> dict[str, Any]:
    await asyncio.sleep(delay_ms / 1000)
    if fail:
        raise HTTPException(status_code=503, detail=f"Transient failure for {target_id}")
    return {
        "target_id": target_id,
        "processed_at": datetime.now(UTC).isoformat(),
        "result": f"detail-for-{target_id}",
        "delay_ms": delay_ms,
    }


@app.post("/resilience/flaky")
def flaky(
    key: str = Query(..., min_length=1),
    fail_until: int = Query(default=2, ge=0, le=20),
) -> dict[str, Any]:
    with _fail_state_lock:
        attempts = _fail_state.get(key, 0) + 1
        _fail_state[key] = attempts
    if attempts <= fail_until:
        raise HTTPException(status_code=503, detail=f"Failing attempt {attempts}/{fail_until} for key={key}")
    return {"key": key, "attempts": attempts, "status": "ok_after_retries"}


@app.get("/resilience/timeout")
async def timeout_endpoint(delay_ms: int = Query(default=2500, ge=0, le=15000)) -> dict[str, Any]:
    await asyncio.sleep(delay_ms / 1000)
    return {"delay_ms": delay_ms, "status": "completed"}


@app.post("/echo")
def echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(uuid4()),
        "received_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


@app.get("/stats/summary")
def summary() -> dict[str, Any]:
    failed_orders = [o for o in ORDERS if o["status"] == "failed"]
    pending_orders = [o for o in ORDERS if o["status"] == "pending"]
    ok_orders = [o for o in ORDERS if o["status"] == "ok"]
    return {
        "users_total": len(USERS),
        "orders_total": len(ORDERS),
        "orders_ok": len(ok_orders),
        "orders_pending": len(pending_orders),
        "orders_failed": len(failed_orders),
        "generated_at": time.time(),
    }

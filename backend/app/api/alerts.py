"""Alert management endpoints.

Manages roofer alert preferences and retrieves alert history.
"""

import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.alert_log import AlertLog
from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.schemas.alerts import AlertHistoryResponse, AlertLogResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])


# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time alert delivery."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        """Send a message to all WebSocket connections for a specific user."""
        if user_id in self.active_connections:
            disconnected = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    disconnected.append(ws)
            # Clean up disconnected WebSockets
            for ws in disconnected:
                self.disconnect(user_id, ws)


# Module-level singleton for external access by alert engine
manager = ConnectionManager()


@router.get("/history", response_model=AlertHistoryResponse)
async def get_alert_history(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of alerts per page"),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve paginated alert history for the current roofer.

    Returns alerts ordered by sent_at descending (most recent first),
    with zone context populated from the associated lead zone.
    """
    # Calculate offset
    offset = (page - 1) * page_size

    # Query total count
    count_stmt = (
        select(func.count(AlertLog.id))
        .where(AlertLog.roofer_account_id == current_user.id)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Query alert logs with lead zone join
    stmt = (
        select(AlertLog, LeadZone)
        .join(LeadZone, AlertLog.lead_zone_id == LeadZone.id)
        .where(AlertLog.roofer_account_id == current_user.id)
        .order_by(AlertLog.sent_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Build response with zone context
    alerts = []
    for alert_log, lead_zone in rows:
        alert_response = AlertLogResponse(
            id=alert_log.id,
            lead_zone_id=alert_log.lead_zone_id,
            channel=alert_log.channel,
            sent_at=alert_log.sent_at,
            opened_at=alert_log.opened_at,
            acted_on=alert_log.acted_on,
            zone_score=lead_zone.composite_score,
            zone_h3_index=lead_zone.h3_index,
        )
        alerts.append(alert_response)

    return AlertHistoryResponse(alerts=alerts, total=total)


@router.patch("/{alert_id}/opened")
async def mark_alert_opened(
    alert_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as opened by setting the opened_at timestamp.

    Only the owning roofer can mark their own alerts.
    """
    # Query the alert
    stmt = select(AlertLog).where(AlertLog.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    # Verify ownership
    if alert.roofer_account_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot mark another roofer's alert",
        )

    # Update opened_at if not already set
    if not alert.opened_at:
        alert.opened_at = datetime.utcnow()
        await db.commit()

    return {"status": "success", "opened_at": alert.opened_at}


@router.patch("/{alert_id}/acted")
async def mark_alert_acted(
    alert_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as acted on by setting the acted_on timestamp.

    Only the owning roofer can mark their own alerts.
    """
    # Query the alert
    stmt = select(AlertLog).where(AlertLog.id == alert_id)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    # Verify ownership
    if alert.roofer_account_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot mark another roofer's alert",
        )

    # Update acted_on if not already set
    if not alert.acted_on:
        alert.acted_on = datetime.utcnow()
        await db.commit()

    return {"status": "success", "acted_on": alert.acted_on}


@router.websocket("/stream")
async def websocket_alert_stream(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for real-time alert delivery.

    Authenticates via JWT token in query parameter and maintains
    a persistent connection for pushing new zone alerts.

    The actual alert pushing is done by the alert engine using the
    ConnectionManager singleton.
    """
    # Authenticate the token
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Accept the connection
    await manager.connect(user_id, websocket)

    try:
        # Keep connection alive with periodic pings
        while True:
            # Wait for any client messages (including pings)
            # The actual alert pushing happens via manager.send_to_user()
            # called by the external alert engine
            try:
                # Set a timeout to send periodic pings
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a ping to keep connection alive
                await websocket.send_json({"type": "ping", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)

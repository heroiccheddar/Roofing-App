"""Organization endpoints for team / multi-rep support."""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.models.roofer_account import RooferAccount
from app.schemas.org import OrgCreate, OrgJoin, OrgMember, OrgResponse, OrgDetailResponse

router = APIRouter(prefix="/org", tags=["organization"])


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(6)[:8]


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgResponse:
    if current_user.organization_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already in an organization")

    org = Organization(
        name=body.name,
        invite_code=_generate_invite_code(),
        created_by=current_user.id,
    )
    db.add(org)
    await db.flush()

    current_user.organization_id = org.id
    current_user.org_role = "owner"
    await db.commit()
    await db.refresh(org)

    return OrgResponse(
        id=org.id, name=org.name, invite_code=org.invite_code,
        created_by=org.created_by, created_at=org.created_at,
    )


@router.get("", response_model=OrgDetailResponse)
async def get_org(
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgDetailResponse:
    if current_user.organization_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in any organization")

    stmt = select(Organization).where(Organization.id == current_user.organization_id)
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    members_stmt = select(RooferAccount).where(
        RooferAccount.organization_id == org.id
    )
    members_result = await db.execute(members_stmt)
    members = members_result.scalars().all()

    return OrgDetailResponse(
        id=org.id, name=org.name, invite_code=org.invite_code,
        created_by=org.created_by, created_at=org.created_at,
        members=[
            OrgMember(
                id=m.id, email=m.email, company_name=m.company_name,
                org_role=m.org_role or "member",
            )
            for m in members
        ],
    )


@router.post("/join", response_model=OrgResponse)
async def join_org(
    body: OrgJoin,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgResponse:
    if current_user.organization_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already in an organization")

    stmt = select(Organization).where(Organization.invite_code == body.invite_code)
    result = await db.execute(stmt)
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite code")

    current_user.organization_id = org.id
    current_user.org_role = "member"
    await db.commit()

    return OrgResponse(
        id=org.id, name=org.name, invite_code=org.invite_code,
        created_by=org.created_by, created_at=org.created_at,
    )


@router.post("/leave")
async def leave_org(
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.organization_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in any organization")
    if current_user.org_role == "owner":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Owner cannot leave. Transfer ownership or delete the organization first.",
        )

    current_user.organization_id = None
    current_user.org_role = None
    await db.commit()
    return {"detail": "Left organization"}

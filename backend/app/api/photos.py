"""Pin photo upload, list, and delete endpoints."""

import logging
import uuid as uuid_mod
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.lead_pin import LeadPin
from app.models.pin_photo import PinPhoto
from app.models.roofer_account import RooferAccount
from app.schemas.pin_photo import PinPhotoListResponse, PinPhotoResponse
from app.services.s3_photos import delete_photo, photo_url, upload_photo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/photos", tags=["photos"])

_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
_ALLOWED_TYPES = {"image/jpeg", "image/png"}


async def _get_team_member_ids(
    current_user: RooferAccount, db: AsyncSession
) -> list[UUID] | None:
    """Return all org member IDs if user is in an org, else None."""
    if current_user.organization_id is None:
        return None
    stmt = select(RooferAccount.id).where(
        RooferAccount.organization_id == current_user.organization_id
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


def _photo_to_response(photo: PinPhoto) -> PinPhotoResponse:
    return PinPhotoResponse(
        id=photo.id,
        lead_pin_id=photo.lead_pin_id,
        roofer_account_id=photo.roofer_account_id,
        url=photo_url(photo.s3_key),
        original_filename=photo.original_filename,
        file_size_bytes=photo.file_size_bytes,
        content_type=photo.content_type,
        created_at=photo.created_at,
    )


@router.post("/{pin_id}", response_model=PinPhotoResponse, status_code=status.HTTP_201_CREATED)
async def upload_pin_photo(
    pin_id: UUID,
    file: UploadFile = File(...),
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PinPhotoResponse:
    """Upload a photo to a lead pin. Max 5 MB, JPEG/PNG only."""
    if not settings.S3_PHOTO_BUCKET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo storage not configured",
        )

    # Verify pin exists and belongs to the current user
    stmt = select(LeadPin).where(
        LeadPin.id == pin_id,
        LeadPin.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    pin = result.scalar_one_or_none()
    if pin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead pin not found")

    # Validate content type
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG and PNG files are allowed",
        )

    # Read file and validate size
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 5MB limit",
        )

    # Generate S3 key and upload
    ext = "jpg" if file.content_type == "image/jpeg" else "png"
    s3_key = f"pins/{current_user.id}/{pin_id}/{uuid_mod.uuid4()}.{ext}"
    upload_photo(file_bytes, s3_key, file.content_type)

    # Persist DB record
    photo = PinPhoto(
        lead_pin_id=pin_id,
        roofer_account_id=current_user.id,
        s3_key=s3_key,
        original_filename=file.filename or "photo",
        file_size_bytes=len(file_bytes),
        content_type=file.content_type,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return _photo_to_response(photo)


@router.get("/{pin_id}", response_model=PinPhotoListResponse)
async def list_pin_photos(
    pin_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PinPhotoListResponse:
    """List all photos for a lead pin. Owner and team members can view."""
    # Fetch the pin first without owner filter so team members can also view
    pin_stmt = select(LeadPin).where(LeadPin.id == pin_id)
    pin_result = await db.execute(pin_stmt)
    pin = pin_result.scalar_one_or_none()
    if pin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead pin not found")

    # Allow owner or org team members; otherwise 404 (don't leak pin existence)
    if pin.roofer_account_id != current_user.id:
        member_ids = await _get_team_member_ids(current_user, db)
        if member_ids is None or pin.roofer_account_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Lead pin not found"
            )

    stmt = (
        select(PinPhoto)
        .where(PinPhoto.lead_pin_id == pin_id)
        .order_by(PinPhoto.created_at)
    )
    result = await db.execute(stmt)
    photos = result.scalars().all()

    return PinPhotoListResponse(
        photos=[_photo_to_response(p) for p in photos],
        count=len(photos),
    )


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pin_photo(
    photo_id: UUID,
    current_user: RooferAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a photo. Only the photo owner can delete."""
    stmt = select(PinPhoto).where(
        PinPhoto.id == photo_id,
        PinPhoto.roofer_account_id == current_user.id,
    )
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # Best-effort S3 deletion — log warning on failure but do not block DB cleanup
    try:
        delete_photo(photo.s3_key)
    except Exception:
        logger.warning("Failed to delete S3 object %s", photo.s3_key)

    await db.delete(photo)
    await db.commit()

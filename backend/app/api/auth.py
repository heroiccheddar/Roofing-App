"""Authentication endpoints.

Handles user registration, login, JWT token generation, and password reset.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from geoalchemy2 import Geography, Geometry

from app.config import settings
from app.database import get_db
from app.models.roofer_account import RooferAccount
from app.schemas.auth import AuthRegister, AuthLogin, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        str: Bcrypt hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hashed password

    Returns:
        bool: True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str) -> str:
    """Create a JWT access token.

    Args:
        user_id: User UUID as string to encode in token "sub" claim

    Returns:
        str: Encoded JWT token
    """
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    to_encode = {"sub": user_id, "exp": expire}
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: AuthRegister,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new roofer account.

    Creates a new RooferAccount with hashed password and PostGIS service area polygon.
    The service area is constructed as a circular polygon using the provided center point
    and radius, leveraging PostGIS geography functions for accurate meter-based buffering.

    Args:
        data: Registration data including credentials and service area definition
        db: Database session dependency

    Returns:
        TokenResponse: JWT access token for the newly created account

    Raises:
        HTTPException: 409 if email is already registered
    """
    # Check if email already exists
    stmt = select(RooferAccount).where(RooferAccount.email == data.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash the password
    password_hash = hash_password(data.password)

    # Create service area polygon using PostGIS
    # Strategy: Create a point, cast to geography for meter-based buffer, then cast back to geometry
    # This ensures accurate circular buffer based on kilometers (converted to meters)
    point = func.ST_SetSRID(
        func.ST_MakePoint(data.service_area_lon, data.service_area_lat),
        4326,  # WGS84 coordinate system
    )
    buffered = func.ST_Buffer(
        cast(point, Geography),  # Cast to geography for meter-based buffer
        data.service_area_radius_km * 1000,  # Convert km to meters
    )
    service_area = cast(buffered, Geometry("POLYGON", srid=4326))  # Cast back to geometry

    # Create new roofer account
    new_account = RooferAccount(
        email=data.email,
        password_hash=password_hash,
        company_name=data.company_name,
        phone_number=data.phone_number,
        service_area=service_area,
        subscription_tier="free",
        is_admin=False,
        is_active=True,
    )

    db.add(new_account)
    await db.commit()
    await db.refresh(new_account)

    # Generate JWT token
    access_token = create_access_token(str(new_account.id))

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/login", response_model=TokenResponse)
async def login(
    data: AuthLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return JWT token.

    Verifies credentials, checks account status, updates last login timestamp,
    and returns a JWT access token.

    Args:
        data: Login credentials (email and password)
        db: Database session dependency

    Returns:
        TokenResponse: JWT access token for the authenticated user

    Raises:
        HTTPException: 401 if credentials are invalid
        HTTPException: 403 if account is deactivated
    """
    # Query user by email
    stmt = select(RooferAccount).where(RooferAccount.email == data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Verify user exists and password is correct
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # Generate JWT token
    access_token = create_access_token(str(user.id))

    return TokenResponse(access_token=access_token, token_type="bearer")

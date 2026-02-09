"""FastAPI dependencies for authentication and authorization.

Provides reusable dependencies for token validation and user retrieval.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.roofer_account import RooferAccount

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> RooferAccount:
    """Decode JWT token and return the authenticated RooferAccount.

    Args:
        token: JWT access token from Authorization header
        db: Database session dependency

    Returns:
        RooferAccount: The authenticated user account

    Raises:
        HTTPException: 401 if token is invalid/expired or user not found
        HTTPException: 403 if account is deactivated
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Query the database for the user
    stmt = select(RooferAccount).where(RooferAccount.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    return user


async def get_current_admin(
    current_user: RooferAccount = Depends(get_current_user),
) -> RooferAccount:
    """Require admin privileges.

    Args:
        current_user: The authenticated user from get_current_user dependency

    Returns:
        RooferAccount: The authenticated admin user

    Raises:
        HTTPException: 403 if user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user

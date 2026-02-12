"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base


@pytest.fixture(scope="session")
def database_url():
    """Test database URL - override in CI/CD."""
    return "postgresql+psycopg://postgres:postgres@localhost:5432/stormleads_test"


@pytest_asyncio.fixture(scope="function")
async def db_engine(database_url):
    """Create async engine for tests."""
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncSession:
    """Create async session for tests."""
    async_session = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
def sample_storm_event():
    """Sample storm event data for testing."""
    return {
        "source": "nws",
        "event_type": "hail",
        "latitude": 35.0,
        "longitude": -95.0,
        "intensity": 2.0,
        "event_time": "2024-05-15T18:30:00Z",
    }


@pytest.fixture(scope="function")
def sample_roofer_account():
    """Sample roofer account data for testing."""
    return {
        "email": "test@example.com",
        "phone": "+15551234567",
        "company_name": "Test Roofing Co",
        "subscription_tier": "pro",
    }

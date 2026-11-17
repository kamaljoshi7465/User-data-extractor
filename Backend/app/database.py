import os
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Read PostgreSQL connection URL from .env (or fallback to a default local dev URL)
POSTGRES_URL = os.getenv("POSTGRES_URL")
if not POSTGRES_URL:
    # Default connection to a local PostgreSQL server (user:password@localhost:5432/dbname)
    POSTGRES_URL = "postgresql+asyncpg://arrt_user:arrt_pass@localhost:5432/arrt_db"

# Async engine – echo=False for normal runs, set True for debugging
engine: AsyncEngine = create_async_engine(
    POSTGRES_URL,
    echo=False,
    future=True,
)

# Session factory for dependency injection
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# FastAPI dependency – yields a fresh session per request
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


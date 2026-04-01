"""
Database connection management for AsyncPG and SQLAlchemy async.

Provides AsyncSessionFactory, FastAPI dependency injection,
connection pool configuration, and health check methods.
"""

import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AsyncSessionFactory:
    """
    Factory for creating async SQLAlchemy sessions with connection pooling.

    Manages the lifecycle of database engines and session makers for
    asyncio-based applications.
    """

    def __init__(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
    ):
        """
        Initialize the async session factory.

        Args:
            database_url: PostgreSQL connection string (must use asyncpg driver)
                         Format: postgresql+asyncpg://user:password@host:port/dbname
            echo: Enable SQL query logging (recommended for development only)
            pool_size: Number of connections to keep in the pool
            max_overflow: Maximum overflow connections above pool_size
            pool_recycle: Recycle connections after this many seconds
            pool_pre_ping: Test connections before using them (recommended for production)

        Raises:
            ValueError: If database_url is invalid or missing asyncpg driver
        """
        if not database_url:
            raise ValueError("database_url must be provided")

        if "asyncpg" not in database_url:
            logger.warning(
                "Using non-asyncpg database driver. "
                "Recommended driver: postgresql+asyncpg://..."
            )

        self.database_url = database_url
        self.echo = echo

        # Create async engine with connection pooling
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            # Performance optimizations
            connect_args={
                "server_settings": {
                    "jit": "off",  # Disable JIT for predictable performance
                }
            },
        )

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info(
            f"AsyncSessionFactory initialized with pool_size={pool_size}, "
            f"max_overflow={max_overflow}"
        )

    async def get_session(self) -> AsyncSession:
        """
        Get a new database session.

        Returns:
            AsyncSession: A new SQLAlchemy async session

        Raises:
            SQLAlchemyError: If connection to database fails
        """
        return self.async_session_maker()

    @asynccontextmanager
    async def session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions with automatic cleanup.

        Example:
            async with factory.session_context() as session:
                result = await session.execute(query)

        Yields:
            AsyncSession: A new database session

        Raises:
            SQLAlchemyError: If database operations fail
        """
        session = await self.get_session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Session error, rolling back: {str(e)}")
            raise
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """
        Check database connectivity and health.

        Executes a simple query to verify the connection pool and
        database availability.

        Returns:
            bool: True if database is healthy, False otherwise

        Example:
            is_healthy = await factory.health_check()
            if not is_healthy:
                logger.error("Database connection failed")
        """
        try:
            async with self.session_context() as session:
                await session.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False

    async def dispose(self) -> None:
        """
        Close all connections and dispose of the engine.

        Should be called during application shutdown to gracefully
        close all database connections.

        Example:
            await factory.dispose()
        """
        await self.engine.dispose()
        logger.info("AsyncSessionFactory disposed")


# Global session factory instance
_session_factory: Optional[AsyncSessionFactory] = None


def init_db(
    database_url: str,
    echo: bool = False,
    pool_size: int = 20,
    max_overflow: int = 10,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
) -> AsyncSessionFactory:
    """
    Initialize the global database session factory.

    Should be called once during application startup.

    Args:
        database_url: PostgreSQL connection string with asyncpg driver
        echo: Enable SQL query logging
        pool_size: Number of connections in the pool
        max_overflow: Maximum overflow connections
        pool_recycle: Connection recycle time in seconds
        pool_pre_ping: Test connections before using them

    Returns:
        AsyncSessionFactory: The initialized factory instance

    Raises:
        ValueError: If database_url is invalid
    """
    global _session_factory
    _session_factory = AsyncSessionFactory(
        database_url=database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
    )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for injecting database sessions.

    Should be used in route handlers with FastAPI dependency injection:

    Example:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_db)):
            result = await session.execute(select(Item))
            return result.scalars().all()

    Yields:
        AsyncSession: A new database session for the request

    Raises:
        RuntimeError: If database factory is not initialized
        SQLAlchemyError: If database operations fail
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database factory not initialized. Call init_db() on application startup."
        )

    async with _session_factory.session_context() as session:
        yield session


async def close_db() -> None:
    """
    Close the global database connection pool.

    Should be called during application shutdown to ensure
    all connections are properly closed.

    Example:
        @app.on_event("shutdown")
        async def shutdown():
            await close_db()
    """
    global _session_factory
    if _session_factory is not None:
        await _session_factory.dispose()
        _session_factory = None
        logger.info("Database connections closed")


async def health_check() -> bool:
    """
    Check database health using the global factory.

    Returns:
        bool: True if database is healthy, False otherwise

    Raises:
        RuntimeError: If database factory is not initialized
    """
    if _session_factory is None:
        raise RuntimeError("Database factory not initialized")

    return await _session_factory.health_check()


def get_session_factory() -> AsyncSessionFactory:
    """
    Get the global session factory instance.

    Returns:
        AsyncSessionFactory: The global factory instance

    Raises:
        RuntimeError: If database factory is not initialized
    """
    if _session_factory is None:
        raise RuntimeError("Database factory not initialized")

    return _session_factory

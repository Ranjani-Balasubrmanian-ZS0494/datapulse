from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import settings
import logging

logger = logging.getLogger(__name__)

engine = None
SessionLocal = None


class Base(DeclarativeBase):
    pass


def _create_table_safe(table, eng):
    """Create a single table, skipping if it already exists or on any error."""
    try:
        insp = inspect(eng)
        if insp.has_table(table.name):
            logger.info(f"Table '{table.name}' already exists — skipping.")
            return
        table.create(bind=eng, checkfirst=True)
        logger.info(f"Table '{table.name}' created.")
    except Exception as e:
        logger.warning(f"Could not create table '{table.name}': {e}")


def init_db():
    global engine, SessionLocal
    if not settings.AZURE_SQL_CONN:
        logger.warning("AZURE_SQL_CONN not set — running without database (degraded mode)")
        return
    try:
        engine = create_engine(
            settings.AZURE_SQL_CONN,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        from models import Base as ModelBase
        # Create each table individually so one failure doesn't block the others
        for table in ModelBase.metadata.sorted_tables:
            _create_table_safe(table, engine)

        logger.info("Database initialised.")
    except Exception as e:
        logger.error(f"Database engine init failed: {e} — running in degraded mode")


def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database not initialised (degraded mode)")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

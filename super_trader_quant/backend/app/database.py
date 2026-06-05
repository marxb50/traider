from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    from .models import asset, candle, signal, memory, backtest, notification  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    inspector = inspect(engine)
    if "notification" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("notification")}
        with engine.begin() as connection:
            if "chat_id" not in columns:
                connection.execute(text("ALTER TABLE notification ADD COLUMN chat_id VARCHAR"))
            if "route" not in columns:
                connection.execute(text("ALTER TABLE notification ADD COLUMN route VARCHAR DEFAULT 'primary'"))
            connection.execute(text("UPDATE notification SET route = 'primary' WHERE route IS NULL OR route = ''"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_notification_route ON notification(route)")
            )
    if "signal" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("signal")}
        with engine.begin() as connection:
            if "side" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN side VARCHAR DEFAULT 'long'"))
            if "memory_applied_at" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN memory_applied_at DATETIME"))
            if "alert_level" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_level VARCHAR"))
            if "alert_score" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_score FLOAT"))
            if "alert_probability_pct" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_probability_pct FLOAT"))
            if "alert_sample_size" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_sample_size INTEGER DEFAULT 0"))
            if "alert_avg_bars_to_target" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_avg_bars_to_target FLOAT"))
            if "alert_risk_reward" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_risk_reward FLOAT"))
            if "alert_reason" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN alert_reason VARCHAR"))
            if "data_provider" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN data_provider VARCHAR"))
            if "data_source_status" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN data_source_status VARCHAR"))
            if "data_source_count" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN data_source_count INTEGER DEFAULT 0"))
            if "data_source_reason" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN data_source_reason VARCHAR"))
            if "data_source_audit_json" not in columns:
                connection.execute(text("ALTER TABLE signal ADD COLUMN data_source_audit_json VARCHAR"))
            connection.execute(text("UPDATE signal SET side = 'long' WHERE side IS NULL OR side = ''"))
            connection.execute(text("UPDATE signal SET alert_sample_size = 0 WHERE alert_sample_size IS NULL"))
            connection.execute(text("UPDATE signal SET data_source_count = 0 WHERE data_source_count IS NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_alert_level ON signal(alert_level)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_data_provider ON signal(data_provider)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_signal_data_source_status ON signal(data_source_status)"))
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_identity_idx "
                    "ON signal(asset_symbol, strategy, timeframe, signal_time)"
                )
            )
    if "setupmemory" in inspector.get_table_names():
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_setup_memory_identity_idx "
                    "ON setupmemory(asset_symbol, strategy, timeframe)"
                )
            )


_apply_lightweight_migrations()


def get_session():
    with Session(engine) as session:
        yield session

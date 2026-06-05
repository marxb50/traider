from sqlmodel import Session, SQLModel, create_engine, select
from super_trader_quant.backend.app.engine.memory_engine import (
    memory_consistency_report,
    rebuild_memories,
    update_memory_from_signal,
)
from super_trader_quant.backend.app.models.memory import SetupMemory
from super_trader_quant.backend.app.models.signal import Signal


def test_memory_updates_after_signal_resolution():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        signal = Signal(
            asset_symbol="PETR4.SA",
            market="BR",
            strategy="IFR2",
            timeframe="D1",
            signal_time=__import__("datetime").datetime(2026, 1, 1),
            entry=100,
            stop=95,
            target=110,
            status="success",
            pnl_pct=10,
        )
        session.add(signal)
        session.commit()
        update_memory_from_signal(session, signal)
        session.commit()
        memory = session.exec(select(SetupMemory)).one()
        assert memory.total_signals == 1
        assert memory.successes == 1
        assert memory.win_rate == 1.0
        assert memory.avg_pnl_pct == 10
        assert signal.memory_applied_at is not None


def test_memory_update_is_idempotent():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        signal = Signal(
            asset_symbol="PETR4.SA",
            market="BR",
            strategy="IFR2",
            timeframe="D1",
            signal_time=__import__("datetime").datetime(2026, 1, 1),
            entry=100,
            stop=95,
            target=110,
            status="success",
            pnl_pct=10,
        )
        session.add(signal)
        session.commit()
        update_memory_from_signal(session, signal)
        update_memory_from_signal(session, signal)
        session.commit()
        memory = session.exec(select(SetupMemory)).one()
        assert memory.total_signals == 1
        assert memory.successes == 1


def test_rebuild_memories_restores_consistency():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        signal_a = Signal(
            asset_symbol="PETR4.SA",
            market="BR",
            strategy="IFR2",
            timeframe="D1",
            signal_time=__import__("datetime").datetime(2026, 1, 1),
            entry=100,
            stop=95,
            target=110,
            status="success",
            pnl_pct=10,
        )
        signal_b = Signal(
            asset_symbol="PETR4.SA",
            market="BR",
            strategy="IFR2",
            timeframe="D1",
            signal_time=__import__("datetime").datetime(2026, 1, 2),
            entry=100,
            stop=95,
            target=110,
            status="failure",
            pnl_pct=-5,
        )
        session.add(signal_a)
        session.add(signal_b)
        session.commit()
        session.add(
            SetupMemory(
                asset_symbol="PETR4.SA",
                strategy="IFR2",
                timeframe="D1",
                total_signals=999,
            )
        )
        session.commit()

        before = memory_consistency_report(session)
        stats = rebuild_memories(session)
        after = memory_consistency_report(session)
        memory = session.exec(select(SetupMemory)).one()

    assert before["is_consistent"] is False
    assert stats == {"resolved_signals": 2, "memory_rows": 1}
    assert after["is_consistent"] is True
    assert memory.total_signals == 2
    assert memory.successes == 1
    assert memory.failures == 1

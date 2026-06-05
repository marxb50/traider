from collections import Counter
from sqlmodel import Session, delete, select
from ..models.memory import SetupMemory
from ..models.signal import Signal
from ..time_utils import utc_now_naive


def update_memory_from_signal(session: Session, signal: Signal) -> SetupMemory:
    if signal.status == "open":
        raise ValueError("Não é permitido aplicar memória para sinal ainda aberto")
    statement = select(SetupMemory).where(
        SetupMemory.asset_symbol == signal.asset_symbol,
        SetupMemory.strategy == signal.strategy,
        SetupMemory.timeframe == signal.timeframe,
    )
    memory = session.exec(statement).first()
    if memory is None:
        memory = SetupMemory(asset_symbol=signal.asset_symbol, strategy=signal.strategy, timeframe=signal.timeframe)
        session.add(memory)
        session.flush()
    if signal.memory_applied_at is not None:
        return memory

    memory.total_signals += 1
    if signal.status == "success":
        memory.successes += 1
    elif signal.status == "failure":
        memory.failures += 1
    else:
        memory.expired += 1
    memory.win_rate = memory.successes / memory.total_signals if memory.total_signals else 0.0
    completed = memory.successes + memory.failures + memory.expired
    prior_total = max(completed - 1, 0)
    prior_avg = memory.avg_pnl_pct
    latest_pnl = signal.pnl_pct or 0.0
    memory.avg_pnl_pct = ((prior_avg * prior_total) + latest_pnl) / completed if completed else 0.0
    memory.last_updated = utc_now_naive()
    signal.memory_applied_at = utc_now_naive()
    session.add(memory)
    session.add(signal)
    return memory


def rebuild_memories(session: Session) -> dict[str, int]:
    resolved_signals = session.exec(select(Signal).where(Signal.status != "open")).all()
    session.exec(delete(SetupMemory))
    for signal in resolved_signals:
        signal.memory_applied_at = None
        session.add(signal)
    session.flush()
    for signal in resolved_signals:
        update_memory_from_signal(session, signal)
    session.commit()
    memory_rows = session.exec(select(SetupMemory)).all()
    return {
        "resolved_signals": len(resolved_signals),
        "memory_rows": len(memory_rows),
    }


def memory_consistency_report(session: Session) -> dict[str, object]:
    resolved_signals = session.exec(select(Signal).where(Signal.status != "open")).all()
    memories = session.exec(select(SetupMemory)).all()
    expected = Counter((signal.asset_symbol, signal.strategy, signal.timeframe) for signal in resolved_signals)
    actual = {
        (memory.asset_symbol, memory.strategy, memory.timeframe): memory.total_signals
        for memory in memories
    }
    return {
        "resolved_signals": len(resolved_signals),
        "memory_total_signals": sum(memory.total_signals for memory in memories),
        "expected_rows": len(expected),
        "actual_rows": len(memories),
        "is_consistent": dict(expected) == actual,
    }

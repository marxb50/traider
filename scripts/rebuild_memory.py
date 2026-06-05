from sqlmodel import Session
from super_trader_quant.backend.app.database import engine, init_db
from super_trader_quant.backend.app.engine.memory_engine import rebuild_memories


def main() -> None:
    init_db()
    with Session(engine) as session:
        stats = rebuild_memories(session)
    print(f"Memória reconstruída com sucesso: {stats}")


if __name__ == "__main__":
    main()

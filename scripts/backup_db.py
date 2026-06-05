from __future__ import annotations

import argparse

from super_trader_quant.backend.app.services.backup_service import BackupError, backup_sqlite_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria um backup consistente do SQLite do SUPER_TRADER_QUANT.")
    parser.add_argument("--dest", help="Diretório de destino do backup. Padrão: BACKUP_DIR.")
    parser.add_argument("--label", default="manual", help="Rótulo curto usado no nome do arquivo.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Sai com sucesso se o banco ainda não existir; útil em primeira instalação.",
    )
    args = parser.parse_args()

    try:
        backup_path = backup_sqlite_database(destination_dir=args.dest, label=args.label)
    except BackupError as exc:
        if args.allow_missing and "não encontrado" in str(exc):
            print(f"Backup ignorado: {exc}")
            return
        raise SystemExit(str(exc)) from exc

    print(f"Backup criado: {backup_path}")


if __name__ == "__main__":
    main()

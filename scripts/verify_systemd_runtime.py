from __future__ import annotations

import argparse
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from super_trader_quant.backend.app.config import settings
from scripts.receipt_utils import write_json_receipt


DEFAULT_RECEIPT_FILE = "systemd_runtime_last.json"
COMMON_SERVICE_SNIPPETS = [
    "User=supertrader",
    "WorkingDirectory=/opt/super_trader_quant",
    "EnvironmentFile=/opt/super_trader_quant/.env",
    "UMask=0077",
    "NoNewPrivileges=true",
    "PrivateTmp=true",
    "ProtectSystem=strict",
    "ProtectHome=true",
    "ReadWritePaths=/opt/super_trader_quant/data /opt/super_trader_quant/logs",
    "ProtectKernelTunables=true",
    "ProtectKernelModules=true",
    "ProtectControlGroups=true",
    "RestrictSUIDSGID=true",
    "LockPersonality=true",
]


SERVICE_EXPECTATIONS = {
    "super-trader-quant-api.service": {
        "show": {
            "LoadState": {"loaded"},
            "ActiveState": {"active"},
            "SubState": {"running"},
            "UnitFileState": {"enabled"},
            "FragmentPath": {"/etc/systemd/system/super-trader-quant-api.service"},
        },
        "snippets": [
            *COMMON_SERVICE_SNIPPETS,
            "Type=simple",
            "ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.run_api",
        ],
    },
    "super-trader-quant-scheduler.service": {
        "show": {
            "LoadState": {"loaded"},
            "ActiveState": {"active"},
            "SubState": {"running"},
            "UnitFileState": {"enabled"},
            "FragmentPath": {"/etc/systemd/system/super-trader-quant-scheduler.service"},
        },
        "snippets": [
            *COMMON_SERVICE_SNIPPETS,
            "Type=simple",
            "ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.run_scheduler",
        ],
    },
    "super-trader-quant-watchdog.service": {
        "show": {
            "LoadState": {"loaded"},
            "UnitFileState": {"static"},
            "FragmentPath": {"/etc/systemd/system/super-trader-quant-watchdog.service"},
        },
        "snippets": [
            *COMMON_SERVICE_SNIPPETS,
            "Type=oneshot",
            "ExecStart=/opt/super_trader_quant/.venv/bin/python -m scripts.watchdog_once --strict",
        ],
    },
    "super-trader-quant-watchdog.timer": {
        "show": {
            "LoadState": {"loaded"},
            "ActiveState": {"active"},
            "SubState": {"waiting"},
            "UnitFileState": {"enabled"},
            "FragmentPath": {"/etc/systemd/system/super-trader-quant-watchdog.timer"},
        },
        "snippets": [
            "OnBootSec=2min",
            "OnUnitActiveSec=5min",
            "Unit=super-trader-quant-watchdog.service",
            "WantedBy=timers.target",
        ],
    },
}


def _run_systemctl(*args: str) -> str:
    result = subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or f"systemctl {' '.join(args)} falhou"
        raise RuntimeError(stderr)
    return result.stdout


def _systemctl_show(unit: str, properties: list[str]) -> dict[str, str]:
    output = _run_systemctl("show", unit, *(f"--property={name}" for name in properties), "--no-pager")
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _systemctl_cat(unit: str) -> str:
    return _run_systemctl("cat", unit, "--no-pager")


def build_systemd_runtime_report(*, run_id: str | None = None) -> dict[str, Any]:
    unit_reports: dict[str, Any] = {}
    issues: list[str] = []

    for unit_name, expectation in SERVICE_EXPECTATIONS.items():
        try:
            show_values = _systemctl_show(unit_name, list(expectation["show"].keys()))
            cat_text = _systemctl_cat(unit_name)
        except RuntimeError as exc:
            unit_reports[unit_name] = {
                "ok": False,
                "error": str(exc),
            }
            issues.append(f"{unit_name}: {exc}")
            continue

        property_failures = []
        for property_name, allowed_values in expectation["show"].items():
            actual_value = show_values.get(property_name, "")
            if actual_value not in allowed_values:
                property_failures.append(
                    {
                        "property": property_name,
                        "actual": actual_value,
                        "allowed": sorted(allowed_values),
                    }
                )

        missing_snippets = [snippet for snippet in expectation["snippets"] if snippet not in cat_text]
        unit_ok = not property_failures and not missing_snippets
        unit_reports[unit_name] = {
            "ok": unit_ok,
            "show": show_values,
            "property_failures": property_failures,
            "missing_snippets": missing_snippets,
        }
        if property_failures:
            issues.extend(
                f"{unit_name}: propriedade {failure['property']} fora do esperado ({failure['actual']!r})"
                for failure in property_failures
            )
        if missing_snippets:
            issues.extend(f"{unit_name}: trecho ausente no unit efetivo -> {snippet}" for snippet in missing_snippets)

    return {
        "ok": not issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "hostname": socket.gethostname(),
        "app_env": settings.app_env,
        "units": unit_reports,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifica em runtime se as units systemd instaladas mantêm o isolamento esperado.")
    parser.add_argument("--run-id", help="Identificador opcional da rodada de verificação.")
    parser.add_argument("--output", help="Salva o JSON completo em um arquivo.")
    args = parser.parse_args()

    report = build_systemd_runtime_report(run_id=args.run_id)
    output_path = Path(args.output) if args.output else settings.resolved_log_dir / DEFAULT_RECEIPT_FILE
    write_json_receipt(output_path, report)

    print(f"ok: {report['ok']}")
    for unit_name, unit_report in report["units"].items():
        print(f"- {unit_name}: {unit_report['ok']}")
        if unit_report.get("error"):
            print(f"  error: {unit_report['error']}")
        if unit_report.get("property_failures"):
            print(f"  property_failures: {unit_report['property_failures']}")
        if unit_report.get("missing_snippets"):
            print(f"  missing_snippets: {unit_report['missing_snippets']}")
    print(f"receipt: {output_path}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()

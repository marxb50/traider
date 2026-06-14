from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "SUPER_TRADER_QUANT"
    app_env: str = "local"
    database_url: str = f"sqlite:///{(DATA_DIR / 'super_trader_quant.db').as_posix()}"
    default_provider: str = "simulated"
    api_host: str = "127.0.0.1"
    api_port: int = 8010
    scan_interval_minutes: int = 30
    scan_timeframe: str = "D1"
    scan_intraday_period: str = "3mo"
    scan_daily_period: str = "1y"
    scan_weekly_period: str = "2y"
    scan_markets: str = "BR,US,UK"
    signal_alert_min_level: str = "yellow"
    signal_alert_prior_weight: float = 8.0
    signal_alert_yellow_min_probability: float = 0.5
    signal_alert_green_min_probability: float = 0.58
    signal_alert_yellow_min_sample_size: int = 6
    signal_alert_green_min_sample_size: int = 10
    signal_alert_yellow_min_avg_pnl_pct: float = -0.25
    signal_alert_green_min_avg_pnl_pct: float = 0.0
    signal_alert_min_risk_reward: float = 1.2
    outcome_check_interval_minutes: int = 30
    notification_dispatch_interval_minutes: int = 5
    notification_max_attempts: int = 5
    notification_batch_size: int = 100
    immediate_notification_batch_size: int = 5000
    max_open_signal_age_days: int = 30
    watchdog_stale_open_signals_alert_min_count: int = 5
    max_pending_notification_age_minutes: int = 30
    watchdog_interval_minutes: int = 5
    watchdog_alert_dedupe_minutes: int = 60
    scheduler_startup_grace_seconds: int = 120
    maintenance_interval_minutes: int = 1440
    sent_notification_retention_days: int = 30
    failed_notification_retention_days: int = 90
    min_free_disk_mb: int = 512
    max_database_size_mb: int = 2048
    backup_retention_days: int = 30
    backup_retention_max_files: int = 60
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""
    telegram_br_bot_token: str = ""
    telegram_br_chat_ids: str = ""
    ops_admin_token: str = ""
    stooq_api_key: str = ""
    brapi_token: str = ""
    brapi_base_url: str = "https://brapi.dev/api"
    bcb_sgs_base_url: str = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
    signal_data_confirmation_mode: str = "auto"
    signal_data_confirmation_provider: str = "brapi"
    signal_data_confirmation_markets: str = "BR"
    signal_data_confirmation_max_close_diff_pct: float = 0.5
    signal_data_confirmation_max_timestamp_drift_hours: float = 3.0
    log_level: str = "INFO"
    log_dir: str = str(ROOT_DIR / "logs")
    scheduler_lock_path: str = str(DATA_DIR / "scheduler.lock")
    backup_dir: str = str(DATA_DIR / "backups")
    report_data_sources: str = ""
    report_logo_path: str = ""
    report_output_dir: str = str(DATA_DIR / "reports")
    report_expected_records: int = 780

    @property
    def telegram_chat_id_list(self) -> list[str]:
        return [item.strip() for item in self.telegram_chat_ids.split(",") if item.strip()]

    @property
    def telegram_br_chat_id_list(self) -> list[str]:
        return [item.strip() for item in self.telegram_br_chat_ids.split(",") if item.strip()]

    @property
    def scan_market_list(self) -> list[str]:
        return [item.strip().upper() for item in self.scan_markets.split(",") if item.strip()]

    @property
    def signal_alert_min_level_normalized(self) -> str:
        return self.signal_alert_min_level.strip().lower()

    @property
    def signal_data_confirmation_mode_normalized(self) -> str:
        mode = self.signal_data_confirmation_mode.strip().lower()
        return mode if mode in {"off", "auto", "strict"} else "auto"

    @property
    def signal_data_confirmation_market_list(self) -> list[str]:
        return [
            item.strip().upper()
            for item in self.signal_data_confirmation_markets.split(",")
            if item.strip()
        ]

    @property
    def resolved_log_dir(self) -> Path:
        path = Path(self.log_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_scheduler_lock_path(self) -> Path:
        path = Path(self.scheduler_lock_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_backup_dir(self) -> Path:
        path = Path(self.backup_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_report_output_dir(self) -> Path:
        path = Path(self.report_output_dir)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()

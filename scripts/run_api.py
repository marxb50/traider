import uvicorn
from super_trader_quant.backend.app.config import settings
from super_trader_quant.backend.app.logging_config import configure_logging


def main() -> None:
    configure_logging("api")
    uvicorn.run(
        "super_trader_quant.backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

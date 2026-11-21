import uvicorn

from config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "todo_app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()

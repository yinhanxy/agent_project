from pathlib import Path

from app.core import logger_handler


def test_backend_logger_writes_under_root_log_backend():
    repo_root = Path(__file__).resolve().parents[2]

    assert Path(logger_handler.logs_dir).resolve() == repo_root / "log" / "backend"


def test_backend_file_handler_uses_backend_log_directory():
    repo_root = Path(__file__).resolve().parents[2]
    logger = logger_handler.get_logger(name="pytest_logger_path")

    file_handlers = [
        handler
        for handler in logger.handlers
        if hasattr(handler, "baseFilename")
    ]

    assert file_handlers
    assert Path(file_handlers[-1].baseFilename).resolve().parent == repo_root / "log" / "backend"

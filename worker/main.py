"""Worker entry point."""
from worker.celery_config import app

if __name__ == "__main__":
    app.start()

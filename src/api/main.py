from fastapi import FastAPI

from src.api.routes.mentor_feedback import router as mentor_feedback_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Golubator Backend API",
        version="0.1.0",
        description="API для сохранения фидбека ментора после созвона",
    )
    app.include_router(mentor_feedback_router)
    return app


app = create_app()

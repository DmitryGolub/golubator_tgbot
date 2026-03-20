from fastapi import FastAPI

from src.api.routes.export_feedback import router as export_feedback_router
from src.api.routes.mentor import router as mentor_router
from src.api.routes.survey import router as survey_router
from src.api.routes.user import router as user_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Golubator Backend API",
        version="0.1.0",
        description="API для опроса после завершения созвона",
    )
    app.include_router(survey_router)
    app.include_router(mentor_router)
    app.include_router(export_feedback_router)
    app.include_router(user_router)
    return app


app = create_app()

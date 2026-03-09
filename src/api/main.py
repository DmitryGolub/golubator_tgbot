from fastapi import FastAPI

from src.api.routes.survey import router as survey_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Golubator Backend API",
        version="0.1.0",
        description="API для опроса после завершения созвона",
    )
    app.include_router(survey_router)
    return app


app = create_app()

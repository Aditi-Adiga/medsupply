from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

from app.api.routes import health, demand, shortage, operations


app = FastAPI(
    title="Medical Supply Intelligence",
    description="AI-powered medical demand forecasting and shortage risk prediction",
    version="1.0.0",
)

app.include_router(operations.router, prefix="/api/v1", tags=["Hospital operations"])

app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origins,
                   allow_credentials=False, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])

@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(
    health.router,
    prefix="/api/v1",
    tags=["Health"],
)

app.include_router(
    demand.router,
    prefix="/api/v1",
    tags=["Demand Forecasting"],
)

app.include_router(
    shortage.router,
    prefix="/api/v1",
    tags=["Shortage Risk"],
)


@app.get("/")
def root():
    return {
        "message": "Medical Supply Intelligence API",
        "version": "1.0.0",
    }

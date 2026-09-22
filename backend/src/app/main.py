from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.companies import router as companies_router
from app.api.company_candidates import router as company_candidates_router
from app.api.company_identity import router as company_identity_router
from app.api.verifications import router as verifications_router
from app.core.config import get_settings
from app.db.session import get_db

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.include_router(companies_router)
app.include_router(company_candidates_router)
app.include_router(company_identity_router)
app.include_router(verifications_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.environment,
    }


@app.get("/api/health/database")
def database_health(
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.execute(text("SELECT 1"))

    return {
        "database": "ok",
    }

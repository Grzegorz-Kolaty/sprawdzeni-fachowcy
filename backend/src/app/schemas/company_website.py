from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class CompanyWebsiteCreate(BaseModel):
    canonical_url: HttpUrl
    brand_id: int | None = None


class CompanyWebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    brand_id: int | None
    domain: str
    canonical_url: str
    created_at: datetime
    updated_at: datetime

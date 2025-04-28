from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AssetBase(BaseModel):
    """
    Base schema for asset data.
    """

    name: str
    description: Optional[str] = None
    asset_type: str
    value: float
    currency: str = "USD"


class AssetCreate(AssetBase):
    """
    Schema for asset creation.
    """

    pass


class AssetUpdate(BaseModel):
    """
    Schema for asset update.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    asset_type: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None


class AssetResponse(AssetBase):
    """
    Schema for asset response.
    """

    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TransactionBase(BaseModel):
    """
    Base schema for transaction data.
    """

    amount: float
    currency: str = "USD"
    transaction_type: str
    description: Optional[str] = None
    date: datetime = datetime.utcnow()
    asset_id: Optional[int] = None


class TransactionCreate(TransactionBase):
    """
    Schema for transaction creation.
    """

    pass


class TransactionUpdate(BaseModel):
    """
    Schema for transaction update.
    """

    amount: Optional[float] = None
    currency: Optional[str] = None
    transaction_type: Optional[str] = None
    description: Optional[str] = None
    date: Optional[datetime] = None
    asset_id: Optional[int] = None


class TransactionResponse(TransactionBase):
    """
    Schema for transaction response.
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

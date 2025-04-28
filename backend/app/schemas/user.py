from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """
    Base schema for user data.
    """

    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    """
    Schema for user creation.
    """

    password: str


class UserUpdate(BaseModel):
    """
    Schema for user update.
    """

    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """
    Schema for user response.
    """

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

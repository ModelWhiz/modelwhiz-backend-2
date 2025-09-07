from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_database import get_async_db
from typing import Optional

router = APIRouter()

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    rememberMe: Optional[bool] = False

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    confirmPassword: str
    acceptTerms: bool

@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    # Implement actual authentication logic
    # Verify credentials against database
    # Generate JWT token
    return {
        "token": "your-jwt-token",
        "user": {
            "id": "user-id",
            "email": request.email,
            "username": "username"
        }
    }

@router.post("/signup")  # Changed from /register
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_async_db)):
    # Implement user registration logic
    # Hash password, save to database
    return {
        "message": "User registered successfully",
        "user": {
            "id": "new-user-id",
            "email": request.email,
            "username": request.username
        }
    }

@router.get("/check-username")
async def check_username(username: str, db: AsyncSession = Depends(get_async_db)):
    # Check if username is available in database
    # Query database for existing username
    available = True  # Replace with actual check
    return {"available": available}

@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}
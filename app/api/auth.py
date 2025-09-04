from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.post("/login")
def login():
    return {"token": "mock-token"}

@router.post("/logout")
def logout():
    return {"message": "User logged out successfully"}

@router.post("/register")
def register():
    return {"message": "User registered successfully"}

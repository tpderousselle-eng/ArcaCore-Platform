from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {
        "message": "Welcome to ArcaCore!",
        "status": "online"
    }


@router.get("/health")
def health():
    return {
        "status": "healthy"
    }
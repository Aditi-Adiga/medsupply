from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "medical-supply-intelligence",
    }
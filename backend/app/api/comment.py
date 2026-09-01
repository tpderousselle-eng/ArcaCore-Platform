from fastapi import APIRouter

router = APIRouter(
    prefix="/comments",
    tags=["Comment"],
)


@router.get("/")
def list_comments():
    return {
        "message": "Comment router generated successfully."
    }
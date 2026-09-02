from fastapi import APIRouter

router = APIRouter(
    prefix="/users",
    tags=["User"],
)


@router.get("/")
def list_users():
    return {"message": "User router generated successfully."}

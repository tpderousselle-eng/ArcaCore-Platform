from fastapi import APIRouter

router = APIRouter(
    prefix="/customers",
    tags=["Customer"],
)


@router.get("/")
def list_customers():
    return {"message": "Customer router generated successfully."}

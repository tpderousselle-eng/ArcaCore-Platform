from fastapi import APIRouter

router = APIRouter(
    prefix="/orders",
    tags=["Order"],
)


@router.get("/")
def list_orders():
    return {"message": "Order router generated successfully."}

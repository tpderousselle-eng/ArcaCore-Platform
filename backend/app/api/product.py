from fastapi import APIRouter

router = APIRouter(
    prefix="/products",
    tags=["Product"],
)


@router.get("/")
def list_products():
    return {"message": "Product router generated successfully."}

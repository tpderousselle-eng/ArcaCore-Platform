from fastapi import APIRouter

router = APIRouter(
    prefix="/invoices",
    tags=["Invoice"],
)


@router.get("/")
def list_invoices():
    return {"message": "Invoice router generated successfully."}

from fastapi import APIRouter

router = APIRouter(
    prefix="/testmodels",
    tags=["Testmodel"],
)


@router.get("/")
def list_testmodels():
    return {"message": "Testmodel router generated successfully."}

from fastapi import APIRouter, Depends

from backend.app.auth.permissions import require_admin
from backend.app.models.user import User

router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
)


@router.get("/dashboard")
def admin_dashboard(
    current_user: User = Depends(require_admin),
):
    return {
        "message": "Welcome to the admin dashboard.",
        "user": current_user.email,
        "role": current_user.role,
    }
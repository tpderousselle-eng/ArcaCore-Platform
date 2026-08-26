from fastapi import APIRouter, Depends
import traceback

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.roles import Role
from backend.app.models.user import User
from backend.app.security.permissions import require_role

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    try:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
        }
    except Exception:
        traceback.print_exc()
        raise


@router.get("/admin")
def admin_panel(
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        return {
            "message": "Welcome Admin!",
            "user": current_user.email,
        }
    except Exception:
        traceback.print_exc()
        raise
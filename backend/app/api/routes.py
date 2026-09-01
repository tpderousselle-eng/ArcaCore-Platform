from fastapi import APIRouter

from backend.app.admin import (
    router as admin_router,
)
from backend.app.auth.change_password import (
    router as change_password_router,
)
from backend.app.auth.forgot_password import (
    router as forgot_password_router,
)
from backend.app.auth.login import (
    router as login_router,
)
from backend.app.auth.me import (
    router as me_router,
)
from backend.app.auth.register import (
    router as register_router,
)
from backend.app.auth.resend_verification import (
    router as resend_verification_router,
)
from backend.app.auth.reset_password import (
    router as reset_password_router,
)
from backend.app.auth.verify_email import (
    router as verify_email_router,
)
from backend.app.organization_invitations import (
    router as organization_invitations_router,
)
from backend.app.organization_members import (
    router as organization_members_router,
)
from backend.app.organizations import (
    router as organizations_router,
)
from backend.app.api.project import (
    router as projects_router,
)
from backend.app.users import (
    router as users_router,
)
from backend.app.workspace_members import (
    router as workspace_members_router,
)
from backend.app.workspaces import (
    router as workspaces_router,
)

router = APIRouter()


@router.get("/")
def root():
    return {
        "message": "Welcome to ArcaCore!",
        "status": "online",
    }


@router.get("/health")
def health():
    return {
        "status": "healthy",
    }


# Authentication
router.include_router(register_router)
router.include_router(login_router)
router.include_router(me_router)
router.include_router(verify_email_router)
router.include_router(forgot_password_router)
router.include_router(reset_password_router)
router.include_router(resend_verification_router)
router.include_router(change_password_router)

# Administration
router.include_router(admin_router)

# Users
router.include_router(users_router)

# Organizations
router.include_router(organizations_router)

# Organization Members
router.include_router(organization_members_router)

# Organization Invitations
router.include_router(organization_invitations_router)

# Workspaces
router.include_router(workspaces_router)

# Workspace Members
router.include_router(workspace_members_router)

# Projects
router.include_router(projects_router)
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.auth import (
    MessageResponse,
    ResetPasswordRequest,
)
from backend.app.services.password_reset_service import (
    PasswordResetService,
)

router = APIRouter(
    tags=["Authentication"],
)


@router.get(
    "/reset-password",
    response_class=HTMLResponse,
)
def reset_password_page(token: str):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reset Password</title>
        <style>
            body {{
                font-family: Arial;
                max-width: 500px;
                margin: 60px auto;
                padding: 20px;
            }}

            input {{
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                box-sizing: border-box;
            }}

            button {{
                width: 100%;
                padding: 12px;
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }}
        </style>
    </head>

    <body>

        <h2>Reset your password</h2>

        <form id="resetForm">

            <input
                type="password"
                id="password"
                placeholder="New Password"
                required
            />

            <button type="submit">
                Reset Password
            </button>

        </form>

        <script>

        document
            .getElementById("resetForm")
            .addEventListener("submit", async (e) => {{

                e.preventDefault();

                const password =
                    document.getElementById("password").value;

                const response = await fetch(
                    "/auth/reset-password",
                    {{
                        method: "POST",
                        headers: {{
                            "Content-Type": "application/json"
                        }},
                        body: JSON.stringify({{
                            token: "{token}",
                            password: password
                        }})
                    }}
                );

                const data = await response.json();

                alert(data.message);

            }});

        </script>

    </body>
    </html>
    """


@router.post(
    "/auth/reset-password",
    response_model=MessageResponse,
)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    password_reset_service = PasswordResetService(db)

    success = password_reset_service.reset_password(
        request.token,
        request.password,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired password reset token.",
        )

    return MessageResponse(
        message="Password has been reset successfully."
    )
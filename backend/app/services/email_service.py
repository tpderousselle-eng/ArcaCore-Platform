import os

import resend


class EmailService:
    def __init__(self):
        resend.api_key = os.getenv("RESEND_API_KEY")

        self.from_email = os.getenv("FROM_EMAIL")
        self.app_url = os.getenv("APP_URL")

    # ---------------------------------------------------------
    # Email Verification
    # ---------------------------------------------------------

    def send_verification_email(
        self,
        to_email: str,
        token: str,
    ):
        verify_link = (
            f"{self.app_url}/verify-email?token={token}"
        )

        resend.Emails.send(
            {
                "from": self.from_email,
                "to": [to_email],
                "subject": "Verify your email",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <body style="font-family: Arial, sans-serif; line-height:1.6;">

                    <h2>Welcome to ArcaCore!</h2>

                    <p>
                        Thank you for creating your account.
                    </p>

                    <p>
                        Please click the button below to verify your email.
                    </p>

                    <p>
                        <a
                            href="{verify_link}"
                            style="
                                background:#2563eb;
                                color:white;
                                padding:12px 20px;
                                text-decoration:none;
                                border-radius:6px;
                                display:inline-block;
                            "
                        >
                            Verify Email
                        </a>
                    </p>

                    <p>
                        If the button doesn't work, copy this link into
                        your browser:
                    </p>

                    <p>{verify_link}</p>

                </body>
                </html>
                """,
            }
        )

    # ---------------------------------------------------------
    # Password Reset
    # ---------------------------------------------------------

    def send_password_reset_email(
        self,
        to_email: str,
        token: str,
    ):
        reset_link = (
            f"{self.app_url}/reset-password?token={token}"
        )

        resend.Emails.send(
            {
                "from": self.from_email,
                "to": [to_email],
                "subject": "Reset your ArcaCore password",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <body style="font-family: Arial, sans-serif; line-height:1.6;">

                    <h2>Password Reset Request</h2>

                    <p>
                        We received a request to reset your password.
                    </p>

                    <p>
                        If you made this request, click the button below.
                    </p>

                    <p>
                        <a
                            href="{reset_link}"
                            style="
                                background:#dc2626;
                                color:white;
                                padding:12px 20px;
                                text-decoration:none;
                                border-radius:6px;
                                display:inline-block;
                            "
                        >
                            Reset Password
                        </a>
                    </p>

                    <p>
                        This link expires in one hour.
                    </p>

                    <p>
                        If you didn't request a password reset,
                        you can safely ignore this email.
                    </p>

                    <p>
                        Or copy this link into your browser:
                    </p>

                    <p>{reset_link}</p>

                </body>
                </html>
                """,
            }
        )
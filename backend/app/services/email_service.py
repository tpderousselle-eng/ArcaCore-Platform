import os
import resend


class EmailService:
    def __init__(self):
        resend.api_key = os.getenv("RESEND_API_KEY")

        self.from_email = os.getenv("FROM_EMAIL")
        self.frontend_url = os.getenv("FRONTEND_URL")

    def send_verification_email(
        self,
        to_email: str,
        token: str,
    ):
        verify_link = f"{self.frontend_url}/verify-email?token={token}"

        resend.Emails.send(
            {
                "from": self.from_email,
                "to": [to_email],
                "subject": "Verify your email",
                "html": f"""
                <h2>Welcome to ArcaCore!</h2>

                <p>Please verify your email address.</p>

                <p>
                    <a href="{verify_link}">
                        Verify Email
                    </a>
                </p>

                <p>Or copy this link into your browser:</p>

                <p>{verify_link}</p>
                """,
            }
        )
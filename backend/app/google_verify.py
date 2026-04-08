from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import google_client_id_list


def verify_google_id_token(token: str) -> dict:
    """Validate ID token and return claims. Tries each configured OAuth client ID as audience."""
    ids = google_client_id_list()
    if not ids:
        raise ValueError("GOOGLE_CLIENT_IDS is not configured on the server")
    request = google_requests.Request()
    last_error: str | None = None
    for aud in ids:
        try:
            info = id_token.verify_oauth2_token(token, request, audience=aud)
            if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
                raise ValueError("Invalid token issuer")
            return info
        except ValueError as e:
            last_error = str(e)
    raise ValueError(last_error or "Invalid Google ID token")

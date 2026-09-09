"""
Google Drive OAuth2 사용자 1회 로그인 승인 모듈
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def run_oauth_flow():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    client_secrets_path = os.path.join(base_dir, "client_secrets.json")
    token_path = os.path.join(base_dir, "token.json")

    if not os.path.exists(client_secrets_path):
        print("client_secrets.json not found", flush=True)
        return False

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, DRIVE_SCOPES)
    custom_msg = "\n--- [AUTH_URL] ---\n{url}\n--- [END_AUTH_URL] ---\n"

    creds = flow.run_local_server(
        host="localhost",
        port=8080,
        prompt="consent",
        access_type="offline",
        authorization_prompt_message=custom_msg,
        open_browser=True,
    )

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"SUCCESS: Saved {token_path}", flush=True)
    return True


if __name__ == "__main__":
    run_oauth_flow()

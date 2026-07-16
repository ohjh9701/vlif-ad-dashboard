"""
빌리프 광고 대시보드 - 사용자 계정 생성 스크립트
"""

import getpass
from datetime import date
import bcrypt
import gspread
from google.oauth2.service_account import Credentials
import toml

SHEET_URL = "https://docs.google.com/spreadsheets/d/11CyqrC-4VIwxaiTzJBJjfyxWb8ARlbjBmfAVIZd3KNU/edit"
SECRETS_PATH = ".streamlit/secrets.toml"

VALID_ROLES = ["admin", "guest"]


def get_worksheet():
    with open(SECRETS_PATH, "r") as f:
        secrets = toml.load(f)
    credentials = Credentials.from_service_account_info(
        secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(credentials)
    return client.open_by_url(SHEET_URL).worksheet("users")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def main():
    print("=" * 50)
    print("빌리프 광고 대시보드 - 사용자 계정 생성")
    print("=" * 50)

    user_id = input("아이디: ").strip()
    if not user_id:
        print("❌ 아이디는 필수입니다.")
        return

    password = getpass.getpass("비밀번호: ")
    password_confirm = getpass.getpass("비밀번호 확인: ")

    if password != password_confirm:
        print("❌ 비밀번호가 일치하지 않습니다.")
        return

    if len(password) < 8:
        print("❌ 비밀번호는 8자 이상이어야 합니다.")
        return

    name = input("표시할 이름: ").strip() or user_id

    # 권한 선택
    print("\n권한을 선택하세요:")
    print("  1) admin  - 모든 기능 사용 가능")
    print("  2) guest  - 대시보드 조회만 가능")
    role_choice = input("선택 (1 또는 2): ").strip()
    if role_choice == "1":
        role = "admin"
    elif role_choice == "2":
        role = "guest"
    else:
        print("❌ 잘못된 선택입니다. 1 또는 2를 입력하세요.")
        return

    print("\n시트에 접근 중...")
    ws = get_worksheet()

    existing = ws.get_all_records()
    existing_ids = [row.get("아이디") for row in existing]
    if user_id in existing_ids:
        print(f"❌ '{user_id}'는 이미 존재하는 아이디입니다.")
        return

    hashed = hash_password(password)

    # 시트 순서: 아이디, 비밀번호해시, 이름, 권한, 활성, 생성일
    ws.append_row([
        user_id,
        hashed,
        name,
        role,
        "TRUE",
        date.today().strftime("%Y-%m-%d"),
    ])

    print(f"\n✅ '{user_id}' 계정이 생성되었습니다.")
    print(f"   이름: {name}")
    print(f"   권한: {role}")
    print(f"   생성일: {date.today()}")
    print("\n이제 앱에서 로그인 가능합니다.")


if __name__ == "__main__":
    main()
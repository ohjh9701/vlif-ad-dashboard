"""
빌리프 광고 대시보드 - 사용자 계정 생성 스크립트

사용법:
    python create_user.py

주의:
    - 이 스크립트는 로컬에서만 실행하세요 (Codespace 또는 본인 PC)
    - 실행 후 비번은 화면에 표시되지 않고 시트에 해시로만 저장됩니다
    - 이 파일은 GitHub에 올려도 됨 (비번 자체는 코드에 없음)
"""

import getpass
from datetime import date
import bcrypt
import gspread
from google.oauth2.service_account import Credentials
import toml

# ─────────────────────────────────
# 설정 로드
# ─────────────────────────────────
SHEET_URL = "https://docs.google.com/spreadsheets/d/11CyqrC-4VIwxaiTzJBJjfyxWb8ARlbjBmfAVIZd3KNU/edit"
SECRETS_PATH = ".streamlit/secrets.toml"


def get_worksheet():
    """secrets.toml에서 인증 정보 읽어서 users 시트 반환."""
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
    """비밀번호를 bcrypt로 해싱."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def main():
    print("=" * 50)
    print("빌리프 광고 대시보드 - 사용자 계정 생성")
    print("=" * 50)
    
    # 입력 받기
    user_id = input("아이디: ").strip()
    if not user_id:
        print("❌ 아이디는 필수입니다.")
        return
    
    # getpass: 비번 입력 시 화면에 표시되지 않음 (Java의 Console.readPassword와 동일)
    password = getpass.getpass("비밀번호: ")
    password_confirm = getpass.getpass("비밀번호 확인: ")
    
    if password != password_confirm:
        print("❌ 비밀번호가 일치하지 않습니다.")
        return
    
    if len(password) < 8:
        print("❌ 비밀번호는 8자 이상이어야 합니다.")
        return
    
    name = input("표시할 이름: ").strip() or user_id
    
    # 시트 접근
    print("\n시트에 접근 중...")
    ws = get_worksheet()
    
    # 아이디 중복 확인
    existing = ws.get_all_records()
    existing_ids = [row.get("아이디") for row in existing]
    if user_id in existing_ids:
        print(f"❌ '{user_id}'는 이미 존재하는 아이디입니다.")
        return
    
    # 비번 해싱
    hashed = hash_password(password)
    
    # 시트에 추가
    ws.append_row([
        user_id,
        hashed,
        name,
        "TRUE",
        date.today().strftime("%Y-%m-%d"),
    ])
    
    print(f"\n✅ '{user_id}' 계정이 생성되었습니다.")
    print(f"   이름: {name}")
    print(f"   생성일: {date.today()}")
    print("\n이제 앱에서 로그인 가능합니다.")


if __name__ == "__main__":
    main()
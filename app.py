"""
빌리프 광고 주간 리포트 시스템
Phase 2-A: 앱 뼈대 + 로그인 + 리포트 목록
"""

import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import date, datetime, timedelta
import bcrypt
import re


# ═══════════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="빌리프 광고 주간 리포트",
    page_icon="📋",
    layout="wide",
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/11CyqrC-4VIwxaiTzJBJjfyxWb8ARlbjBmfAVIZd3KNU/edit"
SESSION_HOURS = 24


# ═══════════════════════════════════════════════════════════
# 📅 날짜 처리 유틸
# ═══════════════════════════════════════════════════════════

DATE_PATTERN = re.compile(r'^\s*(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*$')


def parse_date(s):
    if s is None:
        return None
    if isinstance(s, date):
        return s
    if pd.isna(s):
        return None
    match = DATE_PATTERN.match(str(s))
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_date(d):
    if d is None:
        return ""
    return f"{d.year}. {d.month}. {d.day}"


# ═══════════════════════════════════════════════════════════
# 구글 시트 접근
# ═══════════════════════════════════════════════════════════

@st.cache_resource
def get_gspread_client():
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credentials)


def get_worksheet(sheet_name: str):
    return get_gspread_client().open_by_url(SHEET_URL).worksheet(sheet_name)


# ═══════════════════════════════════════════════════════════
# 데이터 로드 (Phase 2-A 필요 최소)
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_users():
    df = pd.DataFrame(get_worksheet("users").get_all_records())
    return df


@st.cache_data(ttl=60)
def load_reports():
    """reports 시트 로드."""
    df = pd.DataFrame(get_worksheet("reports").get_all_records())
    if not df.empty:
        # 날짜 파싱
        for col in ["시작일", "종료일"]:
            if col in df.columns:
                df[f"{col}_dt"] = df[col].apply(parse_date)
    return df


@st.cache_data(ttl=60)
def load_report_data():
    """report_data 시트 로드."""
    df = pd.DataFrame(get_worksheet("report_data").get_all_records())
    if not df.empty:
        for col in ["노출수", "클릭수", "전환수", "비용"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ═══════════════════════════════════════════════════════════
# 🔐 로그인 시스템
# ═══════════════════════════════════════════════════════════

def verify_login(user_id: str, password: str):
    users_df = load_users()
    if users_df.empty:
        return False, "등록된 사용자가 없습니다.", None

    matched = users_df[users_df["아이디"] == user_id]
    if matched.empty:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다.", None

    row = matched.iloc[0]

    if str(row.get("활성", "")).upper() != "TRUE":
        return False, "비활성화된 계정입니다.", None

    stored_hash = row["비밀번호해시"]
    try:
        is_valid = bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("utf-8"),
        )
    except Exception:
        return False, "비밀번호 검증 오류가 발생했습니다.", None

    if not is_valid:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다.", None

    role = str(row.get("권한", "guest")).lower().strip()
    if role not in ["admin", "guest"]:
        role = "guest"

    return True, row.get("이름", user_id), role


def is_logged_in():
    if "logged_in" not in st.session_state:
        return False
    if not st.session_state.get("logged_in"):
        return False

    login_time = st.session_state.get("login_time")
    if login_time:
        elapsed = datetime.now() - login_time
        if elapsed > timedelta(hours=SESSION_HOURS):
            st.session_state.logged_in = False
            return False

    return True


def show_login_page():
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title("🔐 빌리프 광고 주간 리포트")
        st.caption("로그인이 필요합니다.")
        st.divider()

        with st.form("login_form"):
            user_id = st.text_input("아이디", placeholder="아이디 입력")
            password = st.text_input("비밀번호", type="password", placeholder="비밀번호 입력")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)

            if submitted:
                if not user_id or not password:
                    st.error("아이디와 비밀번호를 모두 입력해주세요.")
                else:
                    with st.spinner("로그인 중..."):
                        success, message, role = verify_login(user_id, password)

                    if success:
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_id
                        st.session_state.user_name = message
                        st.session_state.user_role = role
                        st.session_state.login_time = datetime.now()
                        st.rerun()
                    else:
                        st.error(message)


def logout():
    for key in ["logged_in", "user_id", "user_name", "user_role", "login_time"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# ═══════════════════════════════════════════════════════════
# 로그인 체크
# ═══════════════════════════════════════════════════════════

if not is_logged_in():
    show_login_page()
    st.stop()


# ═══════════════════════════════════════════════════════════
# 이하 로그인 성공한 사용자만 접근
# ═══════════════════════════════════════════════════════════

st.title("📋 빌리프 광고 주간 리포트")


# ─────────────────────────────────
# 사이드바
# ─────────────────────────────────
with st.sidebar:
    st.success(f"👤 **{st.session_state.user_name}** 님")

    role = st.session_state.get("user_role", "guest")
    role_label = "🛡️ 관리자" if role == "admin" else "👁️ 게스트"
    st.caption(role_label)
    st.caption(f"로그인: {st.session_state.login_time.strftime('%Y-%m-%d %H:%M')}")

    if st.button("🚪 로그아웃", use_container_width=True):
        logout()
    st.divider()

    if role == "admin":
        menu_options = [
            "📋 리포트 목록",
            # Phase 2-B에서 추가 예정: "➕ 새 리포트 작성"
            # Phase 후에 추가 예정: "🎯 캠페인 관리"
        ]
    else:
        menu_options = ["📋 리포트 목록"]

    page = st.radio("메뉴", menu_options)


# ═══════════════════════════════════════════════════════════
# 📋 리포트 목록 페이지
# ═══════════════════════════════════════════════════════════

if page == "📋 리포트 목록":
    st.header("📋 리포트 목록")

    try:
        reports_df = load_reports()
    except Exception as e:
        st.error(f"리포트 로드 실패: {e}")
        st.stop()

    if reports_df.empty:
        st.info("📌 아직 작성된 리포트가 없습니다.")
        if role == "admin":
            st.caption("Phase 2-B에서 '새 리포트 작성' 메뉴가 추가될 예정입니다.")
    else:
        # 정렬: 시작일 최신순
        if "시작일_dt" in reports_df.columns:
            reports_df = reports_df.sort_values("시작일_dt", ascending=False, na_position="last")

        st.caption(f"총 **{len(reports_df)}**개 리포트")

        # 리스트 카드 형태로 표시
        for _, row in reports_df.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])

                # 왼쪽: 제목
                col1.markdown(f"### {row['주간제목']}")
                col1.caption(f"**{row.get('리포트ID', '')}**")

                # 가운데: 기간
                start = row.get("시작일", "")
                end = row.get("종료일", "")
                col2.markdown(f"📅 **{start}** ~ **{end}**")
                col2.caption(f"생성일: {row.get('생성일', '')}")

                # 오른쪽: 상태 뱃지
                status = row.get("상태", "")
                if status == "발행":
                    col3.success(f"✅ {status}")
                elif status == "임시저장":
                    col3.warning(f"📝 {status}")
                else:
                    col3.info(status)


# ═══════════════════════════════════════════════════════════
# 안내 메시지 (다른 페이지들)
# ═══════════════════════════════════════════════════════════

# Phase 2-B, 2-C 이후 추가될 페이지들
"""
빌리프 광고 주간 리포트 시스템
Phase 2-B: 로그인 + 리포트 목록 + 새 리포트 작성
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
# 데이터 로드
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_users():
    df = pd.DataFrame(get_worksheet("users").get_all_records())
    return df


@st.cache_data(ttl=60)
def load_reports():
    df = pd.DataFrame(get_worksheet("reports").get_all_records())
    if not df.empty:
        for col in ["시작일", "종료일"]:
            if col in df.columns:
                df[f"{col}_dt"] = df[col].apply(parse_date)
    return df


@st.cache_data(ttl=60)
def load_report_data():
    df = pd.DataFrame(get_worksheet("report_data").get_all_records())
    if not df.empty:
        for col in ["노출수", "클릭수", "전환수", "비용"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_media():
    df = pd.DataFrame(get_worksheet("media").get_all_records())
    if not df.empty:
        if "활성" in df.columns:
            df = df[df["활성"].astype(str).str.upper() == "TRUE"]
        if "순서" in df.columns:
            df["순서"] = pd.to_numeric(df["순서"], errors="coerce")
            df = df.sort_values("순서")
    return df


@st.cache_data(ttl=300)
def load_groups():
    df = pd.DataFrame(get_worksheet("groups").get_all_records())
    return df


@st.cache_data(ttl=60)
def load_campaigns():
    df = pd.DataFrame(get_worksheet("campaigns").get_all_records())
    if not df.empty and "예산" in df.columns:
        df["예산"] = pd.to_numeric(df["예산"], errors="coerce")
    return df


# ═══════════════════════════════════════════════════════════
# ID 자동 생성
# ═══════════════════════════════════════════════════════════

def generate_report_id(reports_df):
    """R001, R002... 형식으로 자동 생성."""
    if reports_df.empty or "리포트ID" not in reports_df.columns:
        return "R001"
    nums = reports_df["리포트ID"].astype(str).str.replace("R", "", regex=False)
    nums = pd.to_numeric(nums, errors="coerce").dropna()
    next_num = int(nums.max()) + 1 if not nums.empty else 1
    return f"R{next_num:03d}"


# ═══════════════════════════════════════════════════════════
# 시트 저장 함수
# ═══════════════════════════════════════════════════════════

def append_report(row):
    """reports 시트에 리포트 마스터 한 줄 추가."""
    get_worksheet("reports").append_row([
        row["리포트ID"], row["주간제목"], row["시작일"],
        row["종료일"], row["상태"], row["생성일"],
    ])


def append_report_data_row(row):
    """report_data 시트에 캠페인 성과 한 줄 추가."""
    get_worksheet("report_data").append_row([
        row["리포트ID"], row["그룹"], row["캠페인ID"],
        row["노출수"], row["클릭수"], row["전환수"], row["비용"],
    ])


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
    for key in list(st.session_state.keys()):
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
            "➕ 새 리포트 작성",
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
            st.caption("좌측 '➕ 새 리포트 작성' 메뉴에서 첫 리포트를 만들어보세요.")
    else:
        if "시작일_dt" in reports_df.columns:
            reports_df = reports_df.sort_values("시작일_dt", ascending=False, na_position="last")

        st.caption(f"총 **{len(reports_df)}**개 리포트")

        for _, row in reports_df.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])

                col1.markdown(f"### {row['주간제목']}")
                col1.caption(f"**{row.get('리포트ID', '')}**")

                start = row.get("시작일", "")
                end = row.get("종료일", "")
                col2.markdown(f"📅 **{start}** ~ **{end}**")
                col2.caption(f"생성일: {row.get('생성일', '')}")

                status = row.get("상태", "")
                if status == "발행":
                    col3.success(f"✅ {status}")
                elif status == "임시저장":
                    col3.warning(f"📝 {status}")
                else:
                    col3.info(status)


# ═══════════════════════════════════════════════════════════
# ➕ 새 리포트 작성 페이지
# ═══════════════════════════════════════════════════════════

elif page == "➕ 새 리포트 작성":
    # 권한 체크
    if st.session_state.get("user_role") != "admin":
        st.error("🚫 이 페이지에 접근할 권한이 없습니다.")
        st.stop()

    st.header("➕ 새 리포트 작성")

    try:
        reports_df = load_reports()
        media_df = load_media()
        groups_df = load_groups()
        campaigns_df = load_campaigns()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    # ═══════════════════════════════════════════
    # 세션 상태: 현재 작성 중인 리포트 정보
    # ═══════════════════════════════════════════
    # "리포트 헤더 입력 완료 → 캠페인 데이터 반복 입력"
    # 이 흐름을 세션으로 관리
    if "current_report_id" not in st.session_state:
        st.session_state.current_report_id = None
        st.session_state.current_report_title = None
        st.session_state.current_report_start = None
        st.session_state.current_report_end = None

    # ───────────────────────────────────────────
    # 상태 1: 리포트 헤더 아직 안 만든 상태 → 헤더 입력 폼
    # ───────────────────────────────────────────
    if st.session_state.current_report_id is None:
        st.subheader("1단계: 리포트 기본 정보")
        st.caption("주간 제목과 기간을 입력하면 새 리포트가 생성됩니다.")

        with st.form("form_report_header"):
            title = st.text_input(
                "주간 보고서 제목",
                placeholder="예: 7월 3주차, 여름 프로모션 첫주",
            )

            col1, col2 = st.columns(2)
            # 기본값: 지난주 금 ~ 이번주 목
            today = date.today()
            days_since_friday = (today.weekday() - 4) % 7
            default_start = today - timedelta(days=days_since_friday + 7)  # 지난주 금
            default_end = default_start + timedelta(days=6)  # 이번주 목

            start_date = col1.date_input("시작일", value=default_start)
            end_date = col2.date_input("종료일", value=default_end)

            submitted = st.form_submit_button("➡️ 다음 (캠페인 데이터 입력)", type="primary")

            if submitted:
                if not title.strip():
                    st.error("주간 제목은 필수입니다.")
                elif end_date < start_date:
                    st.error("종료일이 시작일보다 앞입니다.")
                else:
                    try:
                        new_id = generate_report_id(reports_df)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

                        # 리포트 마스터 저장 (즉시 발행 상태)
                        append_report({
                            "리포트ID": new_id,
                            "주간제목": title.strip(),
                            "시작일": format_date(start_date),
                            "종료일": format_date(end_date),
                            "상태": "발행",
                            "생성일": now_str,
                        })

                        # 세션에 저장
                        st.session_state.current_report_id = new_id
                        st.session_state.current_report_title = title.strip()
                        st.session_state.current_report_start = format_date(start_date)
                        st.session_state.current_report_end = format_date(end_date)

                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"리포트 생성 실패: {e}")

    # ───────────────────────────────────────────
    # 상태 2: 리포트 헤더 만들어짐 → 캠페인 데이터 반복 입력
    # ───────────────────────────────────────────
    else:
        # 현재 작성 중인 리포트 정보 표시
        st.info(
            f"📄 작성 중: **{st.session_state.current_report_title}** "
            f"({st.session_state.current_report_id})  \n"
            f"📅 기간: {st.session_state.current_report_start} ~ {st.session_state.current_report_end}"
        )

        # 종료 버튼
        if st.button("✅ 이 리포트 작성 완료 (새 리포트 시작 가능)"):
            for key in ["current_report_id", "current_report_title",
                        "current_report_start", "current_report_end"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.subheader("2단계: 캠페인 성과 입력")
        st.caption("매체 → 그룹 → 캠페인 순으로 선택 후, 성과 데이터를 입력합니다.")

        # ─── 매체 선택 ───
        if media_df.empty:
            st.error("media 시트에 활성 매체가 없습니다.")
            st.stop()

        media_list = media_df["광고매체"].tolist()
        selected_media = st.selectbox("광고매체", media_list, key="new_media")

        # ─── 그룹 선택 (선택된 매체 소속) ───
        media_groups = groups_df[groups_df["광고매체"] == selected_media] \
            if not groups_df.empty and "광고매체" in groups_df.columns else pd.DataFrame()

        if media_groups.empty:
            st.warning(f"'{selected_media}' 매체에 등록된 그룹이 없습니다.")
            st.stop()

        group_list = media_groups["그룹"].tolist()
        selected_group = st.selectbox("그룹", group_list, key="new_group")

        # ─── 캠페인 선택 (선택된 그룹 소속) ───
        # 활성 캠페인만
        active_campaigns = campaigns_df[
            campaigns_df["활성"].astype(str).str.upper() == "TRUE"
        ] if not campaigns_df.empty else pd.DataFrame()

        group_campaigns = active_campaigns[active_campaigns["그룹"] == selected_group]

        if group_campaigns.empty:
            st.warning(f"'{selected_group}' 그룹에 등록된 활성 캠페인이 없습니다.")
            st.stop()

        campaign_options = {
            f"[{row['캠페인ID']}] {row['캠페인명']}": row['캠페인ID']
            for _, row in group_campaigns.iterrows()
        }
        selected_label = st.selectbox("캠페인", list(campaign_options.keys()), key="new_camp")
        selected_campaign_id = campaign_options[selected_label]
        selected_camp_row = group_campaigns[
            group_campaigns["캠페인ID"] == selected_campaign_id
        ].iloc[0]

        # ─── 예산/유형 자동 표시 ───
        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.info(f"**예산**: ₩{int(selected_camp_row['예산']):,}")
        info_col2.info(f"**유형**: {selected_camp_row['유형']}")
        info_col3.info(f"**URL**: {selected_camp_row['URL']}")

        # ─── 성과 입력 폼 ───
        with st.form("form_campaign_data", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)
            impressions = col1.number_input("노출수", min_value=0, step=1)
            clicks = col2.number_input("클릭수", min_value=0, step=1)
            conversions = col3.number_input("전환수", min_value=0, step=1)
            cost = col4.number_input("비용", min_value=0, step=1000)

            submitted = st.form_submit_button("💾 이 캠페인 데이터 저장", type="primary")

            if submitted:
                try:
                    append_report_data_row({
                        "리포트ID": st.session_state.current_report_id,
                        "그룹": selected_group,
                        "캠페인ID": selected_campaign_id,
                        "노출수": impressions,
                        "클릭수": clicks,
                        "전환수": conversions,
                        "비용": cost,
                    })
                    st.success(
                        f"✅ [{selected_campaign_id}] {selected_camp_row['캠페인명']} "
                        f"데이터 저장 완료!"
                    )
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"저장 실패: {e}")

        # ─── 지금까지 입력된 데이터 요약 ───
        st.divider()
        st.subheader("이 리포트에 지금까지 입력된 캠페인")

        report_data_df = load_report_data()
        current_data = report_data_df[
            report_data_df["리포트ID"] == st.session_state.current_report_id
        ] if not report_data_df.empty else pd.DataFrame()

        if current_data.empty:
            st.caption("아직 입력된 캠페인이 없습니다.")
        else:
            # 캠페인명 조인
            display_df = current_data.merge(
                campaigns_df[["캠페인ID", "캠페인명"]],
                on="캠페인ID", how="left"
            )
            display_cols = ["그룹", "캠페인ID", "캠페인명", "노출수", "클릭수", "전환수", "비용"]
            st.dataframe(
                display_df[display_cols],
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"총 {len(display_df)}개 캠페인 입력됨")
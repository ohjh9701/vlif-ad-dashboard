"""
빌리프 광고 주간 리포트 시스템
Phase 5: 수정/삭제 기능 추가
"""

import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import date, datetime, timedelta
import bcrypt
import re
import os


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

BRAND_COLOR = "#a99a80"
BRAND_COLOR_DARK = "#8b7d67"
BRAND_COLOR_LIGHT = "#e8e0d3"

LOGO_PATH = "assets/vlif_logo.png"


# ═══════════════════════════════════════════════════════════
# 🎨 CSS 스타일
# ═══════════════════════════════════════════════════════════

CUSTOM_CSS = f"""
<style>
    .report-title {{
        color: {BRAND_COLOR_DARK};
        font-weight: 700;
        margin: 0;
    }}
    .report-subtitle {{
        color: {BRAND_COLOR};
        margin: 0;
        font-size: 14px;
    }}
    h2, h3 {{
        color: {BRAND_COLOR_DARK};
    }}

    @media print {{
        [data-testid="stSidebar"] {{ display: none !important; }}
        header {{ display: none !important; }}
        .no-print, .no-print * {{ display: none !important; }}
        .main .block-container {{
            padding: 1rem 1.5rem !important;
            max-width: 100% !important;
        }}
        * {{
            -webkit-print-color-adjust: exact !important;
            color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
        h2 {{ page-break-before: auto; page-break-after: avoid; }}
        h3, h4 {{ page-break-after: avoid; }}
        table, .stDataFrame {{ page-break-inside: avoid; }}
        details {{ display: block !important; }}
        details summary {{ display: none !important; }}
        [data-testid="stForm"],
        [data-testid="stButton"],
        [data-baseweb="select"],
        input, textarea {{
            display: none !important;
        }}
    }}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 로고 헬퍼
# ═══════════════════════════════════════════════════════════

def show_report_header_with_logo():
    if os.path.exists(LOGO_PATH):
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image(LOGO_PATH, width=150)
        with col2:
            st.markdown(
                f"""
                <div style='padding-top: 30px;'>
                    <h2 class='report-title' style='margin: 0; font-size: 24px;'>빌리프성형외과의원</h2>
                    <p class='report-subtitle' style='margin: 5px 0 0 0;'>주간 광고 리포트</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"""
            <div>
                <h2 class='report-title' style='margin: 0;'>빌리프성형외과의원</h2>
                <p class='report-subtitle'>주간 광고 리포트</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
# 데이터 로드 (시트 행 번호 추적을 위한 확장)
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def load_users():
    df = pd.DataFrame(get_worksheet("users").get_all_records())
    return df


@st.cache_data(ttl=60)
def load_reports():
    """
    reports 시트 로드. 시트 행 번호도 함께 저장 (수정/삭제용).
    시트 행 번호 = 헤더 다음부터 시작이므로 index + 2
    """
    df = pd.DataFrame(get_worksheet("reports").get_all_records())
    if not df.empty:
        df["_row"] = df.index + 2  # 시트에서 실제 행 번호
        for col in ["시작일", "종료일"]:
            if col in df.columns:
                df[f"{col}_dt"] = df[col].apply(parse_date)
    return df


@st.cache_data(ttl=60)
def load_report_data():
    df = pd.DataFrame(get_worksheet("report_data").get_all_records())
    if not df.empty:
        df["_row"] = df.index + 2
        for col in ["노출수", "클릭수", "전환수", "비용"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_report_metrics():
    df = pd.DataFrame(get_worksheet("report_metrics").get_all_records())
    if not df.empty:
        df["_row"] = df.index + 2
        if "지표값" in df.columns:
            df["지표값"] = pd.to_numeric(df["지표값"], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_report_comments():
    df = pd.DataFrame(get_worksheet("report_comments").get_all_records())
    if not df.empty:
        df["_row"] = df.index + 2
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


@st.cache_data(ttl=300)
def load_metadata():
    df = pd.DataFrame(get_worksheet("metadata").get_all_records())
    if not df.empty:
        if "활성" in df.columns:
            df = df[df["활성"].astype(str).str.upper() == "TRUE"]
        if "표시순서" in df.columns:
            df["표시순서"] = pd.to_numeric(df["표시순서"], errors="coerce")
            df = df.sort_values(["그룹", "표시순서"])
    return df


def get_metrics_for_group(metadata_df, group):
    return metadata_df[metadata_df["그룹"] == group]["지표종류"].tolist()


# ═══════════════════════════════════════════════════════════
# ID 자동 생성
# ═══════════════════════════════════════════════════════════

def generate_report_id(reports_df):
    if reports_df.empty or "리포트ID" not in reports_df.columns:
        return "R001"
    nums = reports_df["리포트ID"].astype(str).str.replace("R", "", regex=False)
    nums = pd.to_numeric(nums, errors="coerce").dropna()
    next_num = int(nums.max()) + 1 if not nums.empty else 1
    return f"R{next_num:03d}"


# ═══════════════════════════════════════════════════════════
# 시트 저장 (추가)
# ═══════════════════════════════════════════════════════════

def append_report(row):
    get_worksheet("reports").append_row([
        row["리포트ID"], row["주간제목"], row["시작일"],
        row["종료일"], row["상태"], row["생성일"],
    ])


def append_report_data_row(row):
    get_worksheet("report_data").append_row([
        row["리포트ID"], row["그룹"], row["캠페인ID"],
        row["노출수"], row["클릭수"], row["전환수"], row["비용"],
    ])


def append_report_metric(row):
    get_worksheet("report_metrics").append_row([
        row["리포트ID"], row["그룹"], row["지표종류"], row["지표값"],
    ])


def append_report_comment(row):
    get_worksheet("report_comments").append_row([
        row["리포트ID"], row["코멘트내용"], row["작성일시"], row["작성자"],
    ])


# ═══════════════════════════════════════════════════════════
# 시트 수정 (신규)
# ═══════════════════════════════════════════════════════════

def update_report(row_num, values):
    """
    reports 시트의 특정 행 전체 업데이트.
    values: [리포트ID, 주간제목, 시작일, 종료일, 상태, 생성일]
    """
    ws = get_worksheet("reports")
    ws.update(f"A{row_num}:F{row_num}", [values])


def update_report_status(row_num, new_status):
    """reports 시트의 상태 컬럼(E)만 업데이트."""
    ws = get_worksheet("reports")
    ws.update_cell(row_num, 5, new_status)  # E열=5


def update_report_data_row(row_num, values):
    """
    report_data 시트의 특정 행 업데이트.
    values: [리포트ID, 그룹, 캠페인ID, 노출수, 클릭수, 전환수, 비용]
    """
    ws = get_worksheet("report_data")
    ws.update(f"A{row_num}:G{row_num}", [values])


def update_report_metric_row(row_num, values):
    """
    report_metrics 시트의 특정 행 업데이트.
    values: [리포트ID, 그룹, 지표종류, 지표값]
    """
    ws = get_worksheet("report_metrics")
    ws.update(f"A{row_num}:D{row_num}", [values])


def update_report_comment_row(row_num, values):
    """
    report_comments 시트의 특정 행 업데이트.
    values: [리포트ID, 코멘트내용, 작성일시, 작성자]
    """
    ws = get_worksheet("report_comments")
    ws.update(f"A{row_num}:D{row_num}", [values])


# ═══════════════════════════════════════════════════════════
# 시트 삭제 (신규)
# ═══════════════════════════════════════════════════════════

def delete_row(sheet_name, row_num):
    """지정한 시트의 특정 행을 물리 삭제."""
    ws = get_worksheet(sheet_name)
    ws.delete_rows(row_num)


# ═══════════════════════════════════════════════════════════
# 🔄 비교 유틸
# ═══════════════════════════════════════════════════════════

def calc_change_pct(base, target):
    if pd.isna(base) or pd.isna(target):
        return None
    if target == 0:
        if base > 0:
            return None
        return 0
    return (base - target) / target * 100


def format_change_display(base, target, is_currency=False, lower_is_better=False):
    if pd.isna(base) or base == 0:
        base_str = "-"
    elif is_currency:
        base_str = f"₩{int(base):,}"
    else:
        base_str = f"{int(base):,}" if base == int(base) else f"{base:.2f}"

    if pd.isna(target) or target == 0:
        target_str = "-"
    elif is_currency:
        target_str = f"₩{int(target):,}"
    else:
        target_str = f"{int(target):,}" if target == int(target) else f"{target:.2f}"

    if (pd.isna(target) or target == 0) and base > 0:
        return base_str, target_str, "🆕 신규", "gray"

    if (pd.isna(base) or base == 0) and target > 0:
        return base_str, target_str, "❌ 삭제됨", "gray"

    change = calc_change_pct(base, target)
    if change is None or change == 0:
        return base_str, target_str, "→ 0.0%", "gray"

    if change > 0:
        arrow = "▲"
        color = "red" if lower_is_better else "green"
    else:
        arrow = "▼"
        color = "green" if lower_is_better else "red"

    return base_str, target_str, f"{arrow} {change:+.1f}%", color


def render_metric_row(label, base, target, is_currency=False, lower_is_better=False):
    base_str, target_str, change_str, color = format_change_display(
        base, target, is_currency, lower_is_better
    )
    color_html = f":{color}[{change_str}]"

    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    col1.markdown(f"**{label}**")
    col2.markdown(base_str)
    col3.markdown(target_str)
    col4.markdown(color_html)


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
        if os.path.exists(LOGO_PATH):
            logo_col1, logo_col2, logo_col3 = st.columns([1, 2, 1])
            with logo_col2:
                st.image(LOGO_PATH, width=180)
        st.markdown(f"<h1 style='text-align: center; color: {BRAND_COLOR_DARK};'>빌리프 광고 주간 리포트</h1>", unsafe_allow_html=True)
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

if "selected_report_id" not in st.session_state:
    st.session_state.selected_report_id = None

# 삭제 확인 상태 (2단계 삭제용)
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = None  # 예: "report:R001" 또는 "data:5" 형태


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
            "🔄 리포트 비교",
        ]
    else:
        menu_options = ["📋 리포트 목록"]

    page = st.radio("메뉴", menu_options)


# ═══════════════════════════════════════════════════════════
# 📋 리포트 목록 페이지 (또는 상세 조회)
# ═══════════════════════════════════════════════════════════

if page == "📋 리포트 목록":

    if st.session_state.selected_report_id:
        # ═══════════════════════════════════════════
        # 상세 조회 화면
        # ═══════════════════════════════════════════
        report_id = st.session_state.selected_report_id

        try:
            reports_df = load_reports()
            report_data_df = load_report_data()
            report_metrics_df = load_report_metrics()
            report_comments_df = load_report_comments()
            campaigns_df = load_campaigns()
            groups_df = load_groups()
            metadata_df = load_metadata()
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            st.stop()

        matched = reports_df[reports_df["리포트ID"] == report_id]
        if matched.empty:
            st.error(f"리포트 {report_id}를 찾을 수 없습니다.")
            if st.button("⬅️ 목록으로"):
                st.session_state.selected_report_id = None
                st.rerun()
            st.stop()

        report_info = matched.iloc[0]
        report_row_num = int(report_info["_row"])

        # 삭제된 리포트에는 접근 못 하도록
        if report_info.get("상태") == "삭제됨":
            st.warning("⚠️ 이 리포트는 삭제된 상태입니다.")
            if role == "admin":
                if st.button("↩️ 복원하기"):
                    try:
                        update_report_status(report_row_num, "발행")
                        st.success("복원되었습니다.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"복원 실패: {e}")
            if st.button("⬅️ 목록으로"):
                st.session_state.selected_report_id = None
                st.rerun()
            st.stop()

        # ─── 상단 컨트롤 (뒤로가기 + 인쇄 안내) ───
        st.markdown('<div class="no-print">', unsafe_allow_html=True)
        col_back, col_info = st.columns([1, 3])
        with col_back:
            if st.button("⬅️ 목록으로 돌아가기"):
                st.session_state.selected_report_id = None
                st.session_state.confirm_delete = None
                st.rerun()
        with col_info:
            st.info(f"💡 인쇄/PDF 저장은 **Ctrl+P** (Mac: Cmd+P) 를 눌러주세요.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # ─── 브랜드 헤더 ───
        show_report_header_with_logo()

        st.markdown('<hr style="border: 2px solid #a99a80; margin: 20px 0;">', unsafe_allow_html=True)

        # ─── 리포트 헤더 정보 ───
        st.markdown(f"# 📄 {report_info['주간제목']}")
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.markdown(f"📅 **{report_info['시작일']} ~ {report_info['종료일']}**")
        col2.caption(f"리포트ID: {report_id}  |  생성일: {report_info.get('생성일', '')}")
        status = report_info.get("상태", "")
        if status == "발행":
            col3.success(f"✅ {status}")
        elif status == "임시저장":
            col3.warning(f"📝 {status}")
        else:
            col3.info(status)

        # ─── 리포트 마스터 수정/삭제 (관리자만, 인쇄 시 숨김) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)

            with st.expander("⚙️ 리포트 관리 (수정/삭제)"):
                st.markdown("**리포트 정보 수정**")

                with st.form(f"form_edit_report_{report_id}"):
                    e_title = st.text_input(
                        "주간 제목",
                        value=report_info["주간제목"],
                    )
                    ec1, ec2, ec3 = st.columns(3)
                    e_start = ec1.date_input(
                        "시작일",
                        value=parse_date(report_info["시작일"]) or date.today(),
                    )
                    e_end = ec2.date_input(
                        "종료일",
                        value=parse_date(report_info["종료일"]) or date.today(),
                    )
                    e_status = ec3.selectbox(
                        "상태",
                        ["발행", "임시저장"],
                        index=0 if status == "발행" else 1,
                    )

                    if st.form_submit_button("💾 저장", type="primary"):
                        if not e_title.strip():
                            st.error("주간 제목은 필수입니다.")
                        elif e_end < e_start:
                            st.error("종료일이 시작일보다 앞입니다.")
                        else:
                            try:
                                update_report(
                                    report_row_num,
                                    [
                                        report_id,
                                        e_title.strip(),
                                        format_date(e_start),
                                        format_date(e_end),
                                        e_status,
                                        report_info.get("생성일", ""),
                                    ],
                                )
                                st.success("✅ 리포트 정보가 수정되었습니다.")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"수정 실패: {e}")

                st.divider()
                st.markdown("**⚠️ 리포트 삭제 (소프트 삭제)**")
                st.caption("삭제하면 목록에서 사라지지만, 데이터는 유지되어 나중에 복원 가능합니다.")

                delete_key = f"report:{report_id}"

                if st.session_state.confirm_delete == delete_key:
                    st.warning(f"⚠️ 정말 이 리포트를 삭제하시겠습니까?")
                    del_col1, del_col2 = st.columns(2)
                    if del_col1.button("🗑️ 예, 삭제합니다", type="primary",
                                        key=f"confirm_del_report_{report_id}"):
                        try:
                            update_report_status(report_row_num, "삭제됨")
                            st.session_state.confirm_delete = None
                            st.session_state.selected_report_id = None
                            st.cache_data.clear()
                            st.success("리포트가 삭제되었습니다. 목록으로 이동합니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 실패: {e}")
                    if del_col2.button("취소", key=f"cancel_del_report_{report_id}"):
                        st.session_state.confirm_delete = None
                        st.rerun()
                else:
                    if st.button("🗑️ 리포트 삭제", key=f"del_report_{report_id}"):
                        st.session_state.confirm_delete = delete_key
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        this_data = report_data_df[report_data_df["리포트ID"] == report_id] \
            if not report_data_df.empty else pd.DataFrame()
        this_metrics = report_metrics_df[report_metrics_df["리포트ID"] == report_id] \
            if not report_metrics_df.empty else pd.DataFrame()
        this_comments = report_comments_df[report_comments_df["리포트ID"] == report_id] \
            if not report_comments_df.empty else pd.DataFrame()

        if not this_data.empty and not groups_df.empty:
            this_data = this_data.merge(
                groups_df[["그룹", "광고매체"]], on="그룹", how="left"
            )

        # ─── 매체별 요약 ───
        st.subheader("📋 매체별 요약")

        if this_data.empty:
            st.info("아직 입력된 캠페인 데이터가 없습니다.")
        else:
            for media_name in ["구글", "네이버"]:
                media_data = this_data[this_data["광고매체"] == media_name]
                if media_data.empty:
                    continue

                st.markdown(f"### {media_name}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("노출수", f"{int(media_data['노출수'].sum()):,}")
                c2.metric("클릭수", f"{int(media_data['클릭수'].sum()):,}")
                c3.metric("전환수", f"{int(media_data['전환수'].sum()):,}")
                c4.metric("비용", f"₩{int(media_data['비용'].sum()):,}")

        st.divider()

        # ─── 그룹별 성과 ───
        st.subheader("🎯 그룹별 성과")

        if not this_data.empty:
            group_summary = this_data.groupby(["광고매체", "그룹"]).agg(
                캠페인수=("캠페인ID", "count"),
                노출수=("노출수", "sum"),
                클릭수=("클릭수", "sum"),
                전환수=("전환수", "sum"),
                비용=("비용", "sum"),
            ).reset_index()

            group_summary["CTR(%)"] = (
                group_summary["클릭수"] / group_summary["노출수"] * 100
            ).round(2)
            group_summary["CPC"] = (
                group_summary["비용"] / group_summary["클릭수"]
            ).round(0).astype("Int64")

            st.dataframe(group_summary, use_container_width=True, hide_index=True)
        else:
            st.caption("표시할 데이터가 없습니다.")

        st.divider()

        # ─── 캠페인 세부 데이터 ───
        st.subheader("🔍 캠페인 세부 데이터")

        if not this_data.empty:
            detail = this_data.merge(
                campaigns_df[["캠페인ID", "캠페인명", "예산", "유형"]],
                on="캠페인ID", how="left"
            )
            detail["CTR(%)"] = (detail["클릭수"] / detail["노출수"] * 100).round(2)
            detail["CPC"] = (detail["비용"] / detail["클릭수"]).round(0).astype("Int64")

            for media_name in ["구글", "네이버"]:
                media_detail = detail[detail["광고매체"] == media_name]
                if media_detail.empty:
                    continue

                st.markdown(f"#### {media_name}")
                display_cols = ["그룹", "캠페인ID", "캠페인명", "유형",
                                "노출수", "클릭수", "전환수", "비용", "CTR(%)", "CPC"]
                st.dataframe(
                    media_detail[display_cols].sort_values("비용", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.caption("표시할 데이터가 없습니다.")

        # ─── 캠페인 데이터 수정/삭제 (관리자만, 인쇄 시 숨김) ───
        if role == "admin" and not this_data.empty:
            st.markdown('<div class="no-print">', unsafe_allow_html=True)

            with st.expander("⚙️ 캠페인 데이터 수정/삭제"):
                # 각 캠페인 성과 행마다 수정/삭제 UI
                edit_target = this_data.merge(
                    campaigns_df[["캠페인ID", "캠페인명"]],
                    on="캠페인ID", how="left"
                ).sort_values("비용", ascending=False)

                for _, row in edit_target.iterrows():
                    data_row_num = int(row["_row"])
                    camp_id = row["캠페인ID"]

                    with st.container(border=True):
                        st.markdown(
                            f"**[{camp_id}]** {row.get('캠페인명', '')} "
                            f"({row.get('광고매체', '')} - {row['그룹']})"
                        )

                        # 수정 폼
                        with st.form(f"form_edit_data_{data_row_num}"):
                            ec1, ec2, ec3, ec4 = st.columns(4)
                            new_imp = ec1.number_input(
                                "노출수", min_value=0, step=1,
                                value=int(row["노출수"]) if pd.notna(row["노출수"]) else 0,
                                key=f"imp_{data_row_num}",
                            )
                            new_clk = ec2.number_input(
                                "클릭수", min_value=0, step=1,
                                value=int(row["클릭수"]) if pd.notna(row["클릭수"]) else 0,
                                key=f"clk_{data_row_num}",
                            )
                            new_conv = ec3.number_input(
                                "전환수", min_value=0, step=1,
                                value=int(row["전환수"]) if pd.notna(row["전환수"]) else 0,
                                key=f"conv_{data_row_num}",
                            )
                            new_cost = ec4.number_input(
                                "비용", min_value=0, step=1000,
                                value=int(row["비용"]) if pd.notna(row["비용"]) else 0,
                                key=f"cost_{data_row_num}",
                            )

                            btn_col1, btn_col2 = st.columns([1, 4])
                            if btn_col1.form_submit_button("💾 저장"):
                                try:
                                    update_report_data_row(
                                        data_row_num,
                                        [
                                            report_id, row["그룹"], camp_id,
                                            new_imp, new_clk, new_conv, new_cost,
                                        ],
                                    )
                                    st.success("수정되었습니다.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"수정 실패: {e}")

                        # 삭제 (2단계)
                        del_key = f"data:{data_row_num}"
                        if st.session_state.confirm_delete == del_key:
                            st.warning("정말 삭제하시겠습니까?")
                            dc1, dc2 = st.columns(2)
                            if dc1.button("🗑️ 예, 삭제", key=f"cd_data_{data_row_num}",
                                          type="primary"):
                                try:
                                    delete_row("report_data", data_row_num)
                                    st.session_state.confirm_delete = None
                                    st.cache_data.clear()
                                    st.success("삭제되었습니다.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"삭제 실패: {e}")
                            if dc2.button("취소", key=f"cx_data_{data_row_num}"):
                                st.session_state.confirm_delete = None
                                st.rerun()
                        else:
                            if st.button("🗑️ 삭제", key=f"d_data_{data_row_num}"):
                                st.session_state.confirm_delete = del_key
                                st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        # ─── 캠페인 데이터 추가 (관리자만, 인쇄 시 숨김) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("➕ 캠페인 데이터 추가"):
                media_df = load_media()

                if media_df.empty:
                    st.warning("media 시트에 활성 매체가 없습니다.")
                else:
                    add_media = st.selectbox(
                        "광고매체", media_df["광고매체"].tolist(),
                        key=f"add_media_{report_id}",
                    )
                    add_media_groups = groups_df[groups_df["광고매체"] == add_media]

                    if add_media_groups.empty:
                        st.warning(f"'{add_media}' 매체에 등록된 그룹이 없습니다.")
                    else:
                        add_group = st.selectbox(
                            "그룹", add_media_groups["그룹"].tolist(),
                            key=f"add_group_{report_id}",
                        )
                        active_camps = campaigns_df[
                            campaigns_df["활성"].astype(str).str.upper() == "TRUE"
                        ]
                        add_group_camps = active_camps[active_camps["그룹"] == add_group]

                        if add_group_camps.empty:
                            st.warning(f"'{add_group}' 그룹에 활성 캠페인이 없습니다.")
                        else:
                            add_camp_options = {
                                f"[{r['캠페인ID']}] {r['캠페인명']}": r["캠페인ID"]
                                for _, r in add_group_camps.iterrows()
                            }
                            add_camp_label = st.selectbox(
                                "캠페인", list(add_camp_options.keys()),
                                key=f"add_camp_{report_id}",
                            )
                            add_camp_id = add_camp_options[add_camp_label]

                            with st.form(f"form_add_data_{report_id}", clear_on_submit=True):
                                ac1, ac2, ac3, ac4 = st.columns(4)
                                a_imp = ac1.number_input("노출수", min_value=0, step=1)
                                a_clk = ac2.number_input("클릭수", min_value=0, step=1)
                                a_conv = ac3.number_input("전환수", min_value=0, step=1)
                                a_cost = ac4.number_input("비용", min_value=0, step=1000)

                                if st.form_submit_button("💾 추가", type="primary"):
                                    try:
                                        append_report_data_row({
                                            "리포트ID": report_id,
                                            "그룹": add_group,
                                            "캠페인ID": add_camp_id,
                                            "노출수": a_imp,
                                            "클릭수": a_clk,
                                            "전환수": a_conv,
                                            "비용": a_cost,
                                        })
                                        st.success("추가되었습니다.")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"추가 실패: {e}")

            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # ─── 주요 지표 ───
        st.subheader("📌 주요 지표 (그룹 상세지표)")

        if this_metrics.empty:
            st.caption("입력된 그룹지표가 없습니다.")
        else:
            pivot = this_metrics.pivot_table(
                index="그룹",
                columns="지표종류",
                values="지표값",
                aggfunc="sum",
                fill_value=0,
            )
            st.dataframe(pivot, use_container_width=True)

        # ─── 그룹지표 수정/삭제 (관리자만) ───
        if role == "admin" and not this_metrics.empty:
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("⚙️ 그룹지표 수정/삭제"):
                for _, row in this_metrics.sort_values(["그룹", "지표종류"]).iterrows():
                    metric_row_num = int(row["_row"])

                    with st.container(border=True):
                        st.markdown(f"**{row['그룹']}** · {row['지표종류']}")

                        with st.form(f"form_edit_metric_{metric_row_num}"):
                            new_val = st.number_input(
                                "지표값", min_value=0, step=1,
                                value=int(row["지표값"]) if pd.notna(row["지표값"]) else 0,
                                key=f"mv_{metric_row_num}",
                            )
                            bc1, bc2 = st.columns([1, 4])
                            if bc1.form_submit_button("💾 저장"):
                                try:
                                    update_report_metric_row(
                                        metric_row_num,
                                        [report_id, row["그룹"], row["지표종류"], new_val],
                                    )
                                    st.success("수정되었습니다.")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"수정 실패: {e}")

                        del_key = f"metric:{metric_row_num}"
                        if st.session_state.confirm_delete == del_key:
                            st.warning("정말 삭제하시겠습니까?")
                            dc1, dc2 = st.columns(2)
                            if dc1.button("🗑️ 예, 삭제", key=f"cd_m_{metric_row_num}",
                                          type="primary"):
                                try:
                                    delete_row("report_metrics", metric_row_num)
                                    st.session_state.confirm_delete = None
                                    st.cache_data.clear()
                                    st.success("삭제되었습니다.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"삭제 실패: {e}")
                            if dc2.button("취소", key=f"cx_m_{metric_row_num}"):
                                st.session_state.confirm_delete = None
                                st.rerun()
                        else:
                            if st.button("🗑️ 삭제", key=f"d_m_{metric_row_num}"):
                                st.session_state.confirm_delete = del_key
                                st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        # ─── 그룹지표 추가 (관리자만) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("➕ 그룹지표 추가"):
                if metadata_df.empty:
                    st.warning("metadata 시트에 등록된 지표가 없습니다.")
                else:
                    metric_groups = metadata_df["그룹"].unique().tolist()
                    sel_group = st.selectbox(
                        "그룹", metric_groups, key=f"add_metric_group_{report_id}"
                    )
                    metrics = get_metrics_for_group(metadata_df, sel_group)

                    if not metrics:
                        st.warning("이 그룹에 등록된 지표가 없습니다.")
                    else:
                        with st.form(f"form_add_metric_{report_id}", clear_on_submit=True):
                            st.write(f"**{sel_group}** 그룹의 지표값 입력:")
                            metric_values = {}
                            cols = st.columns(len(metrics))
                            for i, m in enumerate(metrics):
                                metric_values[m] = cols[i].number_input(
                                    m, min_value=0, step=1,
                                    key=f"amv_{report_id}_{m}"
                                )

                            if st.form_submit_button("💾 추가", type="primary"):
                                try:
                                    for m, v in metric_values.items():
                                        append_report_metric({
                                            "리포트ID": report_id,
                                            "그룹": sel_group,
                                            "지표종류": m,
                                            "지표값": v,
                                        })
                                    st.success(f"✅ {sel_group} 그룹 지표 추가 완료!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"저장 실패: {e}")

            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # ─── 코멘트 ───
        st.subheader("💬 코멘트")

        if not this_comments.empty:
            this_comments_sorted = this_comments.sort_values("작성일시", ascending=False)
            for _, c in this_comments_sorted.iterrows():
                comment_row_num = int(c["_row"])

                with st.container(border=True):
                    header_col1, header_col2 = st.columns([3, 1])
                    header_col1.markdown(f"**✍️ {c['작성자']}**")
                    header_col2.caption(f"_{c['작성일시']}_")
                    st.write(c["코멘트내용"])

                    # 관리자면 수정/삭제 (인쇄 시 숨김)
                    if role == "admin":
                        st.markdown('<div class="no-print">', unsafe_allow_html=True)

                        # 수정 UI (편집 모드 토글)
                        edit_key = f"edit_comment_{comment_row_num}"
                        if st.session_state.get(edit_key):
                            with st.form(f"form_edit_c_{comment_row_num}"):
                                new_author = st.text_input(
                                    "작성자", value=c["작성자"],
                                    key=f"ea_{comment_row_num}",
                                )
                                new_content = st.text_area(
                                    "코멘트 내용", value=c["코멘트내용"],
                                    height=120,
                                    key=f"ec_{comment_row_num}",
                                )
                                fc1, fc2 = st.columns(2)
                                if fc1.form_submit_button("💾 저장"):
                                    try:
                                        update_report_comment_row(
                                            comment_row_num,
                                            [
                                                report_id,
                                                new_content.strip(),
                                                c["작성일시"],
                                                new_author or c["작성자"],
                                            ],
                                        )
                                        st.session_state[edit_key] = False
                                        st.cache_data.clear()
                                        st.success("수정되었습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"수정 실패: {e}")
                                if fc2.form_submit_button("취소"):
                                    st.session_state[edit_key] = False
                                    st.rerun()
                        else:
                            btn_col1, btn_col2, _ = st.columns([1, 1, 4])
                            if btn_col1.button("✏️ 수정", key=f"ebtn_{comment_row_num}"):
                                st.session_state[edit_key] = True
                                st.rerun()

                            del_key = f"comment:{comment_row_num}"
                            if st.session_state.confirm_delete == del_key:
                                st.warning("정말 삭제하시겠습니까?")
                                dc1, dc2 = st.columns(2)
                                if dc1.button("🗑️ 예", key=f"cd_c_{comment_row_num}",
                                              type="primary"):
                                    try:
                                        delete_row("report_comments", comment_row_num)
                                        st.session_state.confirm_delete = None
                                        st.cache_data.clear()
                                        st.success("삭제되었습니다.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"삭제 실패: {e}")
                                if dc2.button("취소", key=f"cx_c_{comment_row_num}"):
                                    st.session_state.confirm_delete = None
                                    st.rerun()
                            else:
                                if btn_col2.button("🗑️", key=f"dbtn_{comment_row_num}"):
                                    st.session_state.confirm_delete = del_key
                                    st.rerun()

                        st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.caption("아직 코멘트가 없습니다.")

        # ─── 새 코멘트 작성 (관리자만) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("➕ 새 코멘트 작성"):
                with st.form(f"form_add_comment_{report_id}", clear_on_submit=True):
                    author = st.text_input(
                        "작성자", value=st.session_state.user_name,
                        key=f"nc_author_{report_id}",
                    )
                    content = st.text_area(
                        "코멘트 내용",
                        placeholder="예: 이번 주 영미권 CTR이 전주 대비 2배 상승...",
                        height=150,
                        key=f"nc_content_{report_id}",
                    )
                    if st.form_submit_button("💾 저장", type="primary"):
                        if not content.strip():
                            st.error("코멘트 내용은 필수입니다.")
                        else:
                            try:
                                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                                append_report_comment({
                                    "리포트ID": report_id,
                                    "코멘트내용": content.strip(),
                                    "작성일시": now_str,
                                    "작성자": author or st.session_state.user_name,
                                })
                                st.success("✅ 코멘트 저장 완료!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"저장 실패: {e}")

            st.markdown('</div>', unsafe_allow_html=True)

    else:
        # ═══════════════════════════════════════════
        # 리포트 목록 화면
        # ═══════════════════════════════════════════
        st.title("📋 빌리프 광고 주간 리포트")
        st.header("📋 리포트 목록")

        try:
            reports_df = load_reports()
        except Exception as e:
            st.error(f"리포트 로드 실패: {e}")
            st.stop()

        # 삭제된 리포트 필터링 옵션
        show_deleted = False
        if role == "admin":
            show_deleted = st.checkbox("🗑️ 삭제된 리포트 포함 보기", value=False)

        # 삭제되지 않은 리포트만 (또는 옵션에 따라 전체)
        if not reports_df.empty and "상태" in reports_df.columns:
            if not show_deleted:
                reports_df = reports_df[reports_df["상태"] != "삭제됨"]

        if reports_df.empty:
            st.info("📌 표시할 리포트가 없습니다.")
            if role == "admin":
                st.caption("좌측 '➕ 새 리포트 작성' 메뉴에서 첫 리포트를 만들어보세요.")
        else:
            if "시작일_dt" in reports_df.columns:
                reports_df = reports_df.sort_values(
                    "시작일_dt", ascending=False, na_position="last"
                )

            st.caption(f"총 **{len(reports_df)}**개 리포트")

            for _, row in reports_df.iterrows():
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1])

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
                    elif status == "삭제됨":
                        col3.error(f"🗑️ {status}")
                    else:
                        col3.info(status)

                    if col4.button("🔍 상세보기", key=f"detail_{row['리포트ID']}"):
                        st.session_state.selected_report_id = row["리포트ID"]
                        st.session_state.confirm_delete = None
                        st.rerun()


# ═══════════════════════════════════════════════════════════
# ➕ 새 리포트 작성 페이지
# ═══════════════════════════════════════════════════════════

elif page == "➕ 새 리포트 작성":
    st.title("📋 빌리프 광고 주간 리포트")

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

    if "current_report_id" not in st.session_state:
        st.session_state.current_report_id = None
        st.session_state.current_report_title = None
        st.session_state.current_report_start = None
        st.session_state.current_report_end = None

    if st.session_state.current_report_id is None:
        st.subheader("1단계: 리포트 기본 정보")
        st.caption("주간 제목과 기간을 입력하면 새 리포트가 생성됩니다.")

        with st.form("form_report_header"):
            title = st.text_input(
                "주간 보고서 제목",
                placeholder="예: 7월 3주차, 여름 프로모션 첫주",
            )

            col1, col2 = st.columns(2)
            today = date.today()
            days_since_friday = (today.weekday() - 4) % 7
            default_start = today - timedelta(days=days_since_friday + 7)
            default_end = default_start + timedelta(days=6)

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

                        append_report({
                            "리포트ID": new_id,
                            "주간제목": title.strip(),
                            "시작일": format_date(start_date),
                            "종료일": format_date(end_date),
                            "상태": "발행",
                            "생성일": now_str,
                        })

                        st.session_state.current_report_id = new_id
                        st.session_state.current_report_title = title.strip()
                        st.session_state.current_report_start = format_date(start_date)
                        st.session_state.current_report_end = format_date(end_date)

                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"리포트 생성 실패: {e}")

    else:
        st.info(
            f"📄 작성 중: **{st.session_state.current_report_title}** "
            f"({st.session_state.current_report_id})  \n"
            f"📅 기간: {st.session_state.current_report_start} ~ {st.session_state.current_report_end}"
        )

        col_btn1, col_btn2 = st.columns([1, 3])
        if col_btn1.button("✅ 작성 완료 (상세 페이지로)"):
            report_id = st.session_state.current_report_id
            for key in ["current_report_id", "current_report_title",
                        "current_report_start", "current_report_end"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.selected_report_id = report_id
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.subheader("2단계: 캠페인 성과 입력")

        if media_df.empty:
            st.error("media 시트에 활성 매체가 없습니다.")
            st.stop()

        media_list = media_df["광고매체"].tolist()
        selected_media = st.selectbox("광고매체", media_list, key="new_media")

        media_groups = groups_df[groups_df["광고매체"] == selected_media] \
            if not groups_df.empty and "광고매체" in groups_df.columns else pd.DataFrame()

        if media_groups.empty:
            st.warning(f"'{selected_media}' 매체에 등록된 그룹이 없습니다.")
            st.stop()

        group_list = media_groups["그룹"].tolist()
        selected_group = st.selectbox("그룹", group_list, key="new_group")

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

        info_col1, info_col2, info_col3 = st.columns(3)
        info_col1.info(f"**예산**: ₩{int(selected_camp_row['예산']):,}")
        info_col2.info(f"**유형**: {selected_camp_row['유형']}")
        info_col3.info(f"**URL**: {selected_camp_row['URL']}")

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

        st.divider()
        st.subheader("이 리포트에 지금까지 입력된 캠페인")

        report_data_df = load_report_data()
        current_data = report_data_df[
            report_data_df["리포트ID"] == st.session_state.current_report_id
        ] if not report_data_df.empty else pd.DataFrame()

        if current_data.empty:
            st.caption("아직 입력된 캠페인이 없습니다.")
        else:
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


# ═══════════════════════════════════════════════════════════
# 🔄 리포트 비교 페이지
# ═══════════════════════════════════════════════════════════

elif page == "🔄 리포트 비교":
    st.title("📋 빌리프 광고 주간 리포트")

    if st.session_state.get("user_role") != "admin":
        st.error("🚫 이 페이지에 접근할 권한이 없습니다.")
        st.stop()

    st.header("🔄 리포트 비교")
    st.caption("두 개의 리포트를 선택하여 지표 변화를 확인합니다.")

    try:
        reports_df = load_reports()
        report_data_df = load_report_data()
        report_metrics_df = load_report_metrics()
        report_comments_df = load_report_comments()
        campaigns_df = load_campaigns()
        groups_df = load_groups()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    # 삭제된 리포트는 비교에서 제외
    if not reports_df.empty and "상태" in reports_df.columns:
        reports_df = reports_df[reports_df["상태"] != "삭제됨"]

    if reports_df.empty or len(reports_df) < 2:
        st.info("비교하려면 최소 2개의 활성 리포트가 필요합니다.")
        st.stop()

    report_options = {
        f"[{row['리포트ID']}] {row['주간제목']} ({row['시작일']} ~ {row['종료일']})": row["리포트ID"]
        for _, row in reports_df.iterrows()
    }

    col1, col2 = st.columns(2)
    base_label = col1.selectbox(
        "🔵 기준 리포트 (최신/이번주)",
        list(report_options.keys()),
        index=0,
        key="cmp_base",
    )
    target_label = col2.selectbox(
        "⚪ 대상 리포트 (비교 대상/지난주)",
        list(report_options.keys()),
        index=1 if len(report_options) > 1 else 0,
        key="cmp_target",
    )

    base_id = report_options[base_label]
    target_id = report_options[target_label]

    if base_id == target_id:
        st.warning("⚠️ 같은 리포트를 선택할 수 없습니다.")
        st.stop()

    show_campaign_detail = st.checkbox(
        "🔍 개별 캠페인 상세 비교 표시", value=False,
        help="개별 캠페인 단위까지 비교 결과를 표시합니다."
    )

    st.divider()

    base_info = reports_df[reports_df["리포트ID"] == base_id].iloc[0]
    target_info = reports_df[reports_df["리포트ID"] == target_id].iloc[0]

    st.markdown(f"### 🔵 기준: {base_info['주간제목']}")
    st.caption(f"{base_info['시작일']} ~ {base_info['종료일']} ({base_id})")
    st.markdown(f"### ⚪ 대상: {target_info['주간제목']}")
    st.caption(f"{target_info['시작일']} ~ {target_info['종료일']} ({target_id})")

    st.divider()

    base_data = report_data_df[report_data_df["리포트ID"] == base_id] \
        if not report_data_df.empty else pd.DataFrame()
    target_data = report_data_df[report_data_df["리포트ID"] == target_id] \
        if not report_data_df.empty else pd.DataFrame()

    if not base_data.empty:
        base_data = base_data.merge(groups_df[["그룹", "광고매체"]], on="그룹", how="left")
    if not target_data.empty:
        target_data = target_data.merge(groups_df[["그룹", "광고매체"]], on="그룹", how="left")

    st.subheader("📋 매체별 요약 변화")

    for media_name in ["구글", "네이버"]:
        base_m = base_data[base_data["광고매체"] == media_name] if not base_data.empty else pd.DataFrame()
        target_m = target_data[target_data["광고매체"] == media_name] if not target_data.empty else pd.DataFrame()

        if base_m.empty and target_m.empty:
            continue

        st.markdown(f"### {media_name}")

        base_sum = {
            "노출수": base_m["노출수"].sum() if not base_m.empty else 0,
            "클릭수": base_m["클릭수"].sum() if not base_m.empty else 0,
            "전환수": base_m["전환수"].sum() if not base_m.empty else 0,
            "비용": base_m["비용"].sum() if not base_m.empty else 0,
        }
        target_sum = {
            "노출수": target_m["노출수"].sum() if not target_m.empty else 0,
            "클릭수": target_m["클릭수"].sum() if not target_m.empty else 0,
            "전환수": target_m["전환수"].sum() if not target_m.empty else 0,
            "비용": target_m["비용"].sum() if not target_m.empty else 0,
        }

        base_ctr = (base_sum["클릭수"] / base_sum["노출수"] * 100) if base_sum["노출수"] else 0
        base_cpc = (base_sum["비용"] / base_sum["클릭수"]) if base_sum["클릭수"] else 0
        target_ctr = (target_sum["클릭수"] / target_sum["노출수"] * 100) if target_sum["노출수"] else 0
        target_cpc = (target_sum["비용"] / target_sum["클릭수"]) if target_sum["클릭수"] else 0

        h1, h2, h3, h4 = st.columns([2, 2, 2, 2])
        h1.markdown("**지표**")
        h2.markdown("**기준**")
        h3.markdown("**대상**")
        h4.markdown("**증감**")

        render_metric_row("노출수", base_sum["노출수"], target_sum["노출수"])
        render_metric_row("클릭수", base_sum["클릭수"], target_sum["클릭수"])
        render_metric_row("전환수", base_sum["전환수"], target_sum["전환수"])
        render_metric_row("비용", base_sum["비용"], target_sum["비용"], is_currency=True, lower_is_better=True)
        render_metric_row("CTR(%)", base_ctr, target_ctr)
        render_metric_row("CPC", base_cpc, target_cpc, is_currency=True, lower_is_better=True)

        st.markdown("")

    st.divider()

    st.subheader("🎯 그룹별 성과 변화")

    all_groups = set()
    if not base_data.empty:
        all_groups.update(base_data[["광고매체", "그룹"]].apply(tuple, axis=1).tolist())
    if not target_data.empty:
        all_groups.update(target_data[["광고매체", "그룹"]].apply(tuple, axis=1).tolist())

    all_groups_sorted = sorted(all_groups, key=lambda x: (x[0] or "", x[1] or ""))

    for media_name, group_name in all_groups_sorted:
        base_g = base_data[
            (base_data["광고매체"] == media_name) & (base_data["그룹"] == group_name)
        ] if not base_data.empty else pd.DataFrame()
        target_g = target_data[
            (target_data["광고매체"] == media_name) & (target_data["그룹"] == group_name)
        ] if not target_data.empty else pd.DataFrame()

        base_sum = {
            "노출수": base_g["노출수"].sum() if not base_g.empty else 0,
            "클릭수": base_g["클릭수"].sum() if not base_g.empty else 0,
            "전환수": base_g["전환수"].sum() if not base_g.empty else 0,
            "비용": base_g["비용"].sum() if not base_g.empty else 0,
        }
        target_sum = {
            "노출수": target_g["노출수"].sum() if not target_g.empty else 0,
            "클릭수": target_g["클릭수"].sum() if not target_g.empty else 0,
            "전환수": target_g["전환수"].sum() if not target_g.empty else 0,
            "비용": target_g["비용"].sum() if not target_g.empty else 0,
        }

        with st.expander(f"**{media_name} - {group_name}**", expanded=True):
            h1, h2, h3, h4 = st.columns([2, 2, 2, 2])
            h1.markdown("**지표**")
            h2.markdown("**기준**")
            h3.markdown("**대상**")
            h4.markdown("**증감**")

            render_metric_row("노출수", base_sum["노출수"], target_sum["노출수"])
            render_metric_row("클릭수", base_sum["클릭수"], target_sum["클릭수"])
            render_metric_row("전환수", base_sum["전환수"], target_sum["전환수"])
            render_metric_row(
                "비용", base_sum["비용"], target_sum["비용"],
                is_currency=True, lower_is_better=True
            )

    st.divider()

    if show_campaign_detail:
        st.subheader("🔍 개별 캠페인 상세 비교")

        all_campaigns = set()
        if not base_data.empty:
            all_campaigns.update(base_data["캠페인ID"].tolist())
        if not target_data.empty:
            all_campaigns.update(target_data["캠페인ID"].tolist())

        for camp_id in sorted(all_campaigns):
            camp_info = campaigns_df[campaigns_df["캠페인ID"] == camp_id]
            if camp_info.empty:
                camp_name = f"(알 수 없음)"
                group_name = "-"
            else:
                camp_name = camp_info.iloc[0]["캠페인명"]
                group_name = camp_info.iloc[0]["그룹"]

            base_c = base_data[base_data["캠페인ID"] == camp_id] if not base_data.empty else pd.DataFrame()
            target_c = target_data[target_data["캠페인ID"] == camp_id] if not target_data.empty else pd.DataFrame()

            base_sum = {
                "노출수": base_c["노출수"].sum() if not base_c.empty else 0,
                "클릭수": base_c["클릭수"].sum() if not base_c.empty else 0,
                "전환수": base_c["전환수"].sum() if not base_c.empty else 0,
                "비용": base_c["비용"].sum() if not base_c.empty else 0,
            }
            target_sum = {
                "노출수": target_c["노출수"].sum() if not target_c.empty else 0,
                "클릭수": target_c["클릭수"].sum() if not target_c.empty else 0,
                "전환수": target_c["전환수"].sum() if not target_c.empty else 0,
                "비용": target_c["비용"].sum() if not target_c.empty else 0,
            }

            with st.expander(f"**[{camp_id}]** {camp_name} ({group_name})"):
                h1, h2, h3, h4 = st.columns([2, 2, 2, 2])
                h1.markdown("**지표**")
                h2.markdown("**기준**")
                h3.markdown("**대상**")
                h4.markdown("**증감**")

                render_metric_row("노출수", base_sum["노출수"], target_sum["노출수"])
                render_metric_row("클릭수", base_sum["클릭수"], target_sum["클릭수"])
                render_metric_row("전환수", base_sum["전환수"], target_sum["전환수"])
                render_metric_row(
                    "비용", base_sum["비용"], target_sum["비용"],
                    is_currency=True, lower_is_better=True
                )

        st.divider()

    st.subheader("📌 주요 지표 변화")

    base_metrics = report_metrics_df[report_metrics_df["리포트ID"] == base_id] \
        if not report_metrics_df.empty else pd.DataFrame()
    target_metrics = report_metrics_df[report_metrics_df["리포트ID"] == target_id] \
        if not report_metrics_df.empty else pd.DataFrame()

    all_metric_keys = set()
    if not base_metrics.empty:
        all_metric_keys.update(base_metrics[["그룹", "지표종류"]].apply(tuple, axis=1).tolist())
    if not target_metrics.empty:
        all_metric_keys.update(target_metrics[["그룹", "지표종류"]].apply(tuple, axis=1).tolist())

    if not all_metric_keys:
        st.caption("표시할 그룹지표가 없습니다.")
    else:
        groups_with_metrics = sorted(set(k[0] for k in all_metric_keys))

        for group_name in groups_with_metrics:
            st.markdown(f"### {group_name}")

            group_metric_keys = sorted([k for k in all_metric_keys if k[0] == group_name])

            h1, h2, h3, h4 = st.columns([2, 2, 2, 2])
            h1.markdown("**지표종류**")
            h2.markdown("**기준**")
            h3.markdown("**대상**")
            h4.markdown("**증감**")

            for _, metric_type in group_metric_keys:
                base_val = base_metrics[
                    (base_metrics["그룹"] == group_name)
                    & (base_metrics["지표종류"] == metric_type)
                ]["지표값"].sum() if not base_metrics.empty else 0

                target_val = target_metrics[
                    (target_metrics["그룹"] == group_name)
                    & (target_metrics["지표종류"] == metric_type)
                ]["지표값"].sum() if not target_metrics.empty else 0

                render_metric_row(metric_type, base_val, target_val)

            st.markdown("")

    st.divider()

    st.subheader("💬 코멘트 (참고용)")

    base_comments = report_comments_df[report_comments_df["리포트ID"] == base_id] \
        if not report_comments_df.empty else pd.DataFrame()
    target_comments = report_comments_df[report_comments_df["리포트ID"] == target_id] \
        if not report_comments_df.empty else pd.DataFrame()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"#### 🔵 {base_info['주간제목']}")
        if base_comments.empty:
            st.caption("코멘트 없음")
        else:
            for _, c in base_comments.sort_values("작성일시", ascending=False).iterrows():
                with st.container(border=True):
                    st.markdown(f"**✍️ {c['작성자']}**")
                    st.caption(f"_{c['작성일시']}_")
                    st.write(c["코멘트내용"])

    with col2:
        st.markdown(f"#### ⚪ {target_info['주간제목']}")
        if target_comments.empty:
            st.caption("코멘트 없음")
        else:
            for _, c in target_comments.sort_values("작성일시", ascending=False).iterrows():
                with st.container(border=True):
                    st.markdown(f"**✍️ {c['작성자']}**")
                    st.caption(f"_{c['작성일시']}_")
                    st.write(c["코멘트내용"])
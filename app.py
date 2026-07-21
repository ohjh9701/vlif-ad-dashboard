"""
빌리프 광고 주간 리포트 시스템
Phase 3: 인쇄/PDF 최적화 스타일링 + 로고 + 브랜드 색상
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

# 브랜드 색상
BRAND_COLOR = "#a99a80"       # 로고 브라운/베이지
BRAND_COLOR_DARK = "#8b7d67"  # 어두운 톤 (헤더용)
BRAND_COLOR_LIGHT = "#e8e0d3" # 밝은 톤 (배경용)

LOGO_PATH = "assets/vlif_logo.png"


# ═══════════════════════════════════════════════════════════
# 🎨 CSS 스타일 (브랜드 + 인쇄)
# ═══════════════════════════════════════════════════════════

CUSTOM_CSS = f"""
<style>
    /* ─── 브랜드 색상 강조 ─── */
    .report-header {{
        border-bottom: 3px solid {BRAND_COLOR};
        padding-bottom: 15px;
        margin-bottom: 25px;
    }}

    .report-header-inner {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}

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

    /* ─── 섹션 헤더 하이라이트 ─── */
    h2, h3 {{
        color: {BRAND_COLOR_DARK};
    }}

    /* ─── 인쇄 스타일 ─── */
    @media print {{
        /* 사이드바 숨김 */
        [data-testid="stSidebar"] {{
            display: none !important;
        }}

        /* 헤더/툴바 숨김 */
        header {{
            display: none !important;
        }}

        /* 인쇄 버튼 숨김 */
        .no-print, .no-print * {{
            display: none !important;
        }}

        /* Streamlit 기본 여백 조정 */
        .main .block-container {{
            padding: 1rem 1.5rem !important;
            max-width: 100% !important;
        }}

        /* 색상 강제 표시 (인쇄 시 색 손실 방지) */
        * {{
            -webkit-print-color-adjust: exact !important;
            color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}

        /* 페이지 나눔 힌트 */
        h2 {{
            page-break-before: auto;
            page-break-after: avoid;
        }}

        h3, h4 {{
            page-break-after: avoid;
        }}

        /* 표는 나눠지지 않게 */
        table, .stDataFrame {{
            page-break-inside: avoid;
        }}

        /* expander 자동 펼침 (인쇄 시 내용이 보이도록) */
        details {{
            display: block !important;
        }}

        details summary {{
            display: none !important;
        }}

        /* 폼 요소, 입력 위젯 숨김 */
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
# 로고 표시 헬퍼
# ═══════════════════════════════════════════════════════════

def show_logo(width=150):
    """로고 파일 표시. 파일 없으면 조용히 스킵."""
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=width)


def show_report_header_with_logo():
    """리포트용 브랜드 헤더 (로고 + 병원명)."""
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


@st.cache_data(ttl=60)
def load_report_metrics():
    df = pd.DataFrame(get_worksheet("report_metrics").get_all_records())
    if not df.empty and "지표값" in df.columns:
        df["지표값"] = pd.to_numeric(df["지표값"], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_report_comments():
    df = pd.DataFrame(get_worksheet("report_comments").get_all_records())
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
# 시트 저장
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
        # 로고 표시
        if os.path.exists(LOGO_PATH):
            logo_col1, logo_col2, logo_col3 = st.columns([1, 2, 1])
            with logo_col2:
                st.image(LOGO_PATH, width=180)
        st.markdown(f"<h1 style='text-align: center; color: {BRAND_COLOR_DARK};'>빌리프 광고 주간 리포트</h1>", unsafe_allow_html=True)
        st.caption("<p style='text-align: center;'>로그인이 필요합니다.</p>", unsafe_allow_html=True)
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
        # 상세 조회 화면 (인쇄 최적화 페이지)
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

        # ─── 인쇄 시 숨길 UI (뒤로가기 + 인쇄 버튼) ───
        st.markdown('<div class="no-print">', unsafe_allow_html=True)
        col_back, col_print = st.columns([3, 1])
        with col_back:
            if st.button("⬅️ 목록으로 돌아가기"):
                st.session_state.selected_report_id = None
                st.rerun()
        with col_print:
            # 인쇄 버튼 (JavaScript로 window.print() 호출)
            st.markdown(
                """
                <button onclick="window.print()" style="
                    background-color: #a99a80;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 600;
                    width: 100%;
                ">🖨️ 인쇄 / PDF 저장</button>
                """,
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        # ─── 브랜드 헤더 (로고 + 병원명) ───
        show_report_header_with_logo()

        st.markdown('<hr style="border: 2px solid #a99a80; margin: 20px 0;">', unsafe_allow_html=True)

        # ─── 리포트 헤더 (제목, 기간, ID) ───
        st.markdown(f"# 📄 {report_info['주간제목']}")
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.markdown(f"📅 **{report_info['시작일']} ~ {report_info['종료일']}**")
        col2.caption(f"리포트ID: {report_id}  |  생성일: {report_info.get('생성일', '')}")
        status = report_info.get("상태", "")
        if status == "발행":
            col3.success(f"✅ {status}")
        else:
            col3.info(status)

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

        st.divider()

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

        # ─── 그룹지표 입력 (인쇄 시 숨김) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("➕ 그룹지표 입력/추가"):
                if metadata_df.empty:
                    st.warning("metadata 시트에 등록된 지표가 없습니다.")
                else:
                    metric_groups = metadata_df["그룹"].unique().tolist()
                    sel_group = st.selectbox(
                        "그룹", metric_groups, key=f"metric_group_{report_id}"
                    )
                    metrics = get_metrics_for_group(metadata_df, sel_group)

                    if not metrics:
                        st.warning("이 그룹에 등록된 지표가 없습니다.")
                    else:
                        with st.form(f"form_metric_{report_id}", clear_on_submit=True):
                            st.write(f"**{sel_group}** 그룹의 지표값 입력:")
                            metric_values = {}
                            cols = st.columns(len(metrics))
                            for i, m in enumerate(metrics):
                                metric_values[m] = cols[i].number_input(
                                    m, min_value=0, step=1,
                                    key=f"m_val_{report_id}_{m}"
                                )

                            submitted = st.form_submit_button("💾 저장", type="primary")
                            if submitted:
                                try:
                                    for m, v in metric_values.items():
                                        append_report_metric({
                                            "리포트ID": report_id,
                                            "그룹": sel_group,
                                            "지표종류": m,
                                            "지표값": v,
                                        })
                                    st.success(f"✅ {sel_group} 그룹 지표 저장 완료!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"저장 실패: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

        st.subheader("💬 코멘트")

        if not this_comments.empty:
            this_comments_sorted = this_comments.sort_values("작성일시", ascending=False)
            for _, c in this_comments_sorted.iterrows():
                with st.container(border=True):
                    header_col1, header_col2 = st.columns([3, 1])
                    header_col1.markdown(f"**✍️ {c['작성자']}**")
                    header_col2.caption(f"_{c['작성일시']}_")
                    st.write(c["코멘트내용"])
        else:
            st.caption("아직 코멘트가 없습니다.")

        # ─── 코멘트 입력 (인쇄 시 숨김) ───
        if role == "admin":
            st.markdown('<div class="no-print">', unsafe_allow_html=True)
            with st.expander("➕ 새 코멘트 작성"):
                with st.form(f"form_comment_{report_id}", clear_on_submit=True):
                    author = st.text_input(
                        "작성자", value=st.session_state.user_name,
                        key=f"c_author_{report_id}",
                    )
                    content = st.text_area(
                        "코멘트 내용",
                        placeholder="예: 이번 주 영미권 CTR이 전주 대비 2배 상승...",
                        height=150,
                        key=f"c_content_{report_id}",
                    )
                    submitted = st.form_submit_button("💾 저장", type="primary")
                    if submitted:
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

        if reports_df.empty:
            st.info("📌 아직 작성된 리포트가 없습니다.")
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
                    else:
                        col3.info(status)

                    if col4.button("🔍 상세보기", key=f"detail_{row['리포트ID']}"):
                        st.session_state.selected_report_id = row["리포트ID"]
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
        if col_btn1.button("✅ 작성 완료 (목록으로)"):
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

    if reports_df.empty or len(reports_df) < 2:
        st.info("비교하려면 최소 2개의 리포트가 필요합니다.")
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
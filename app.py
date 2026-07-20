"""
빌리프 광고 대시보드
날짜 형식 표준: '2026. 7. 1' (마지막 마침표 없음)
"""

import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import date, datetime, timedelta
import calendar
import bcrypt
import re
import plotly.graph_objects as go

# ─────────────────────────────────
# 페이지 설정
# ─────────────────────────────────
st.set_page_config(
    page_title="빌리프 광고 대시보드",
    page_icon="📊",
    layout="wide",
)

SHEET_URL = "https://docs.google.com/spreadsheets/d/11CyqrC-4VIwxaiTzJBJjfyxWb8ARlbjBmfAVIZd3KNU/edit"


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
# 구글 시트 클라이언트
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
# 🔐 로그인 시스템
# ═══════════════════════════════════════════════════════════

SESSION_HOURS = 24


@st.cache_data(ttl=30)
def load_users():
    df = pd.DataFrame(get_worksheet("users").get_all_records())
    return df


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
        st.title("🔐 빌리프 광고 대시보드")
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

        st.caption("💡 계정이 필요하시면 관리자에게 문의하세요.")


def logout():
    for key in ["logged_in", "user_id", "user_name", "user_role", "login_time"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


# 로그인 체크
if not is_logged_in():
    show_login_page()
    st.stop()


# ═══════════════════════════════════════════════════════════
# 이하 로그인 성공한 사용자만 접근
# ═══════════════════════════════════════════════════════════

st.title("📊 빌리프 광고 대시보드")


# ─────────────────────────────────
# 데이터 로드
# ─────────────────────────────────
@st.cache_data(ttl=60)
def load_campaigns():
    df = pd.DataFrame(get_worksheet("campaigns").get_all_records())
    if not df.empty and "예산" in df.columns:
        df["예산"] = pd.to_numeric(df["예산"], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_data():
    df = pd.DataFrame(get_worksheet("data").get_all_records())
    if not df.empty:
        for col in ["노출수", "클릭수", "전환수", "비용"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ["날짜시작", "날짜끝"]:
            if col in df.columns:
                df[f"{col}_dt"] = df[col].apply(parse_date)
    return df


@st.cache_data(ttl=60)
def load_group_metrics():
    df = pd.DataFrame(get_worksheet("group_metrics").get_all_records())
    if not df.empty:
        if "지표값" in df.columns:
            df["지표값"] = pd.to_numeric(df["지표값"], errors="coerce")
        for col in ["날짜시작", "날짜끝"]:
            if col in df.columns:
                df[f"{col}_dt"] = df[col].apply(parse_date)
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


@st.cache_data(ttl=300)
def load_groups():
    return pd.DataFrame(get_worksheet("groups").get_all_records())


@st.cache_data(ttl=60)
def load_comments():
    df = pd.DataFrame(get_worksheet("comments").get_all_records())
    if not df.empty:
        for col in ["년도", "월"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_metrics_for_group(metadata_df, group):
    return metadata_df[metadata_df["그룹"] == group]["지표종류"].tolist()


# ─────────────────────────────────
# ID 자동 생성
# ─────────────────────────────────
def generate_campaign_id(group, campaigns_df, groups_df):
    prefix_row = groups_df[groups_df["그룹"] == group]
    if prefix_row.empty:
        return None
    prefix = prefix_row.iloc[0]["프리픽스"]

    if campaigns_df.empty or "캠페인ID" not in campaigns_df.columns:
        next_num = 1
    else:
        same_group = campaigns_df[campaigns_df["캠페인ID"].astype(str).str.startswith(prefix)]
        if same_group.empty:
            next_num = 1
        else:
            nums = same_group["캠페인ID"].astype(str).str.replace(prefix, "", regex=False)
            nums = pd.to_numeric(nums, errors="coerce").dropna()
            next_num = int(nums.max()) + 1 if not nums.empty else 1

    return f"{prefix}{next_num:02d}"


def generate_comment_id(comments_df):
    if comments_df.empty or "코멘트ID" not in comments_df.columns:
        return "CM001"
    nums = comments_df["코멘트ID"].astype(str).str.replace("CM", "", regex=False)
    nums = pd.to_numeric(nums, errors="coerce").dropna()
    next_num = int(nums.max()) + 1 if not nums.empty else 1
    return f"CM{next_num:03d}"


# ─────────────────────────────────
# 시트 저장
# ─────────────────────────────────
def append_campaign_master(row):
    get_worksheet("campaigns").append_row([
        row["캠페인ID"], row["캠페인명"], row["그룹"],
        row["예산"], row["유형"], row["URL"], row["활성"],
    ])


def append_data_row(row):
    get_worksheet("data").append_row([
        row["날짜시작"], row["날짜끝"], row["캠페인ID"],
        row["노출수"], row["클릭수"], row["전환수"], row["비용"],
    ])


def append_group_metric(row):
    get_worksheet("group_metrics").append_row([
        row["날짜시작"], row["날짜끝"], row["그룹"],
        row["지표종류"], row["지표값"],
    ])


def append_comment(row):
    get_worksheet("comments").append_row([
        row["코멘트ID"], row["년도"], row["월"], row["기간"],
        row["코멘트"], row["작성일시"], row["작성자"],
    ])


# ═══════════════════════════════════════════════════════════
# 📅 기간 유틸
# ═══════════════════════════════════════════════════════════

def get_period_range(year, month, section):
    last_day = calendar.monthrange(year, month)[1]
    if section == "전체":
        return date(year, month, 1), date(year, month, last_day)
    elif section == "상순 (1~10일)":
        return date(year, month, 1), date(year, month, 10)
    elif section == "중순 (11~20일)":
        return date(year, month, 11), date(year, month, 20)
    elif section == "하순 (21~월말)":
        return date(year, month, 21), date(year, month, last_day)


def get_previous_period(year, month, section):
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    return prev_year, prev_month, section


def filter_data_by_period(data_df, year, month, section):
    if data_df.empty:
        return data_df.iloc[0:0]

    curr_start, curr_end = get_period_range(year, month, section)

    if section == "전체":
        df = data_df[
            data_df["날짜시작_dt"].apply(
                lambda d: d is not None and d.year == year and d.month == month
            )
        ]
        return df.copy()
    else:
        df = data_df[
            (data_df["날짜시작_dt"] == curr_start)
            & (data_df["날짜끝_dt"] == curr_end)
        ]
        return df.copy()


def filter_metrics_by_period(metrics_df, year, month, section):
    if metrics_df.empty:
        return metrics_df.iloc[0:0]

    curr_start, curr_end = get_period_range(year, month, section)

    if section == "전체":
        df = metrics_df[
            metrics_df["날짜시작_dt"].apply(
                lambda d: d is not None and d.year == year and d.month == month
            )
        ]
        return df.copy()
    else:
        df = metrics_df[
            (metrics_df["날짜시작_dt"] == curr_start)
            & (metrics_df["날짜끝_dt"] == curr_end)
        ]
        return df.copy()


def get_section_label(section):
    mapping = {
        "전체": "전체",
        "상순 (1~10일)": "상순",
        "중순 (11~20일)": "중순",
        "하순 (21~월말)": "하순",
    }
    return mapping.get(section, section)


# ═══════════════════════════════════════════════════════════
# 📈 트렌드 데이터 처리
# ═══════════════════════════════════════════════════════════

def get_recent_months(base_year: int, base_month: int, n: int = 6):
    """기준 년/월에서 과거 n개월 리스트 반환."""
    months = []
    y, m = base_year, base_month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def _get_section_from_start_day(day: int):
    if day <= 10:
        return "상순"
    elif day <= 20:
        return "중순"
    else:
        return "하순"


def build_trend_data(data_df, campaigns_df, months_list,
                     group_filter=None, campaign_filter=None,
                     x_mode="month"):
    """트렌드 차트용 데이터 생성."""
    if data_df.empty:
        return pd.DataFrame()

    df = data_df.merge(campaigns_df[["캠페인ID", "그룹"]], on="캠페인ID", how="left")

    if group_filter and group_filter != "전체":
        df = df[df["그룹"] == group_filter]
    if campaign_filter:
        df = df[df["캠페인ID"] == campaign_filter]

    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["_year"] = df["날짜시작_dt"].apply(lambda d: d.year if d else None)
    df["_month"] = df["날짜시작_dt"].apply(lambda d: d.month if d else None)
    df["_day"] = df["날짜시작_dt"].apply(lambda d: d.day if d else None)
    df["_section"] = df["_day"].apply(
        lambda x: _get_section_from_start_day(int(x)) if pd.notna(x) else None
    )

    # 대상 월 필터
    target_ym = set(months_list)
    df = df[df.apply(lambda r: (r["_year"], r["_month"]) in target_ym, axis=1)]

    if df.empty:
        return pd.DataFrame()

    if x_mode == "month":
        df["_x"] = df.apply(lambda r: f"{int(r['_year'])}. {int(r['_month'])}", axis=1)
        df["_sort"] = df["_year"] * 100 + df["_month"]
    else:
        section_order = {"상순": 1, "중순": 2, "하순": 3}
        df["_x"] = df.apply(
            lambda r: f"{int(r['_year'])}. {int(r['_month'])} {r['_section']}",
            axis=1
        )
        df["_sort"] = (
            df["_year"] * 10000
            + df["_month"] * 100
            + df["_section"].map(section_order).fillna(9)
        )

    grouped = df.groupby(["_sort", "_x", "그룹"]).agg(
        노출수=("노출수", "sum"),
        클릭수=("클릭수", "sum"),
        전환수=("전환수", "sum"),
        비용=("비용", "sum"),
    ).reset_index()

    return grouped.sort_values("_sort")


# ─────────────────────────────────
# 지표 계산 유틸
# ─────────────────────────────────
def calc_change(current, previous):
    if previous == 0 or pd.isna(previous):
        return None
    return (current - previous) / previous * 100


def format_metric_with_delta(current, previous, is_currency=False):
    if is_currency:
        value_str = f"₩{int(current):,}" if pd.notna(current) else "-"
    else:
        value_str = f"{int(current):,}" if pd.notna(current) else "-"
    delta = calc_change(current, previous)
    delta_str = f"{delta:+.1f}%" if delta is not None else None
    return value_str, delta_str


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
            "📊 대시보드",
            "➕ 데이터 입력",
            "🎯 캠페인 관리",
            "💬 코멘트 관리",
        ]
    else:
        menu_options = ["📊 대시보드"]

    page = st.radio("메뉴", menu_options)


# ═══════════════════════════════════════════════════════════
# 📊 대시보드
# ═══════════════════════════════════════════════════════════
if page == "📊 대시보드":
    try:
        campaigns_df = load_campaigns()
        data_df = load_data()
        metrics_df = load_group_metrics()
        comments_df = load_comments()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    st.subheader("🔎 필터")
    today = date.today()
    r1c1, r1c2, r1c3 = st.columns([1, 1, 2])
    year = r1c1.selectbox("년도", [2026, 2025], index=0)
    month = r1c2.selectbox("월", list(range(1, 13)), index=today.month - 1,
                           format_func=lambda m: f"{m}월")
    section = r1c3.selectbox(
        "기간",
        ["전체", "상순 (1~10일)", "중순 (11~20일)", "하순 (21~월말)"],
        index=0,
    )

    r2c1, r2c2 = st.columns([1, 2])
    group_options = ["전체"] + (
        campaigns_df["그룹"].unique().tolist() if not campaigns_df.empty else []
    )
    selected_group = r2c1.selectbox("그룹", group_options, index=0)

    if selected_group == "전체":
        available_campaigns = campaigns_df
    else:
        available_campaigns = campaigns_df[campaigns_df["그룹"] == selected_group]

    campaign_options_dict = {"전체": None}
    if not available_campaigns.empty:
        for _, row in available_campaigns.iterrows():
            label = f"[{row['캠페인ID']}] {row['캠페인명']}"
            campaign_options_dict[label] = row["캠페인ID"]

    selected_campaign_label = r2c2.selectbox(
        "캠페인", list(campaign_options_dict.keys())
    )
    selected_campaign_id = campaign_options_dict[selected_campaign_label]

    curr_start, curr_end = get_period_range(year, month, section)
    prev_year, prev_month, prev_section = get_previous_period(year, month, section)
    prev_start, prev_end = get_period_range(prev_year, prev_month, prev_section)

    filter_desc = f"**현재**: {format_date(curr_start)} ~ {format_date(curr_end)}"
    filter_desc += f"  |  **비교**: {format_date(prev_start)} ~ {format_date(prev_end)}"
    if selected_group != "전체":
        filter_desc += f"  |  **그룹**: {selected_group}"
    if selected_campaign_id:
        filter_desc += f"  |  **캠페인**: {selected_campaign_label}"
    st.caption(filter_desc)

    curr_data = filter_data_by_period(data_df, year, month, section)
    prev_data = filter_data_by_period(data_df, prev_year, prev_month, prev_section)

    def apply_group_campaign_filter(df):
        if df.empty:
            return df
        if selected_group != "전체" or selected_campaign_id:
            merged = df.merge(
                campaigns_df[["캠페인ID", "그룹"]], on="캠페인ID", how="left"
            )
            if selected_group != "전체":
                merged = merged[merged["그룹"] == selected_group]
            if selected_campaign_id:
                merged = merged[merged["캠페인ID"] == selected_campaign_id]
            return merged.drop(columns=["그룹"])
        return df

    curr_data = apply_group_campaign_filter(curr_data)
    prev_data = apply_group_campaign_filter(prev_data)

    if curr_data.empty:
        st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
        st.stop()

    st.subheader("💬 기간 코멘트")
    section_label = get_section_label(section)
    current_comments = comments_df[
        (comments_df["년도"] == year)
        & (comments_df["월"] == month)
        & (comments_df["기간"] == section_label)
    ] if not comments_df.empty else pd.DataFrame()

    if not current_comments.empty:
        current_comments = current_comments.sort_values("작성일시", ascending=False)
        for _, row in current_comments.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['작성자']}** · _{row['작성일시']}_")
                st.write(row["코멘트"])
    else:
        st.info("이 기간에 대한 코멘트가 아직 없습니다.")

    st.subheader("📋 요약 (전월 동일 기간 대비)")
    curr_totals = {
        "노출수": curr_data["노출수"].sum(),
        "클릭수": curr_data["클릭수"].sum(),
        "전환수": curr_data["전환수"].sum(),
        "비용": curr_data["비용"].sum(),
    }
    prev_totals = {
        "노출수": prev_data["노출수"].sum() if not prev_data.empty else 0,
        "클릭수": prev_data["클릭수"].sum() if not prev_data.empty else 0,
        "전환수": prev_data["전환수"].sum() if not prev_data.empty else 0,
        "비용": prev_data["비용"].sum() if not prev_data.empty else 0,
    }

    c1, c2, c3, c4 = st.columns(4)
    for col, key, is_curr in [
        (c1, "노출수", False), (c2, "클릭수", False),
        (c3, "전환수", False), (c4, "비용", True),
    ]:
        val_str, delta_str = format_metric_with_delta(
            curr_totals[key], prev_totals[key], is_currency=is_curr
        )
        col.metric(key, val_str, delta_str)

    st.subheader("📈 효율 지표")
    curr_ctr = (curr_totals["클릭수"] / curr_totals["노출수"] * 100) if curr_totals["노출수"] else 0
    curr_cpc = (curr_totals["비용"] / curr_totals["클릭수"]) if curr_totals["클릭수"] else 0
    prev_ctr = (prev_totals["클릭수"] / prev_totals["노출수"] * 100) if prev_totals["노출수"] else 0
    prev_cpc = (prev_totals["비용"] / prev_totals["클릭수"]) if prev_totals["클릭수"] else 0

    c1, c2 = st.columns(2)
    ctr_delta = calc_change(curr_ctr, prev_ctr)
    cpc_delta = calc_change(curr_cpc, prev_cpc)
    c1.metric("CTR", f"{curr_ctr:.2f}%",
              f"{ctr_delta:+.1f}%" if ctr_delta is not None else None)
    c2.metric("CPC", f"₩{int(curr_cpc):,}" if curr_cpc else "-",
              f"{cpc_delta:+.1f}%" if cpc_delta is not None else None,
              delta_color="inverse")

# ─────── 📊 트렌드 차트 (최근 6개월) ───────
    st.subheader("📊 트렌드 (최근 6개월)")

    x_mode_label = st.radio(
        "X축 단위",
        ["월별", "순별 (상/중/하순)"],
        horizontal=True,
        key="trend_x_mode",
    )
    x_mode = "month" if x_mode_label == "월별" else "section"

    recent_months = get_recent_months(year, month, n=6)

    trend_df = build_trend_data(
        data_df, campaigns_df, recent_months,
        group_filter=selected_group,
        campaign_filter=selected_campaign_id,
        x_mode=x_mode,
    )

    if trend_df.empty:
        st.info("최근 6개월간 트렌드 데이터가 없습니다.")
    else:
        x_order = trend_df.drop_duplicates("_x").sort_values("_sort")["_x"].tolist()
        groups_in_data = trend_df["그룹"].unique().tolist()

        # ─── 노출수 + 클릭수 (이중 Y축) ───
        fig = go.Figure()

        # 색상 팔레트 (그룹별로 노출수/클릭수가 같은 색 계열)
        color_palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

        for i, g in enumerate(groups_in_data):
            gdf = trend_df[trend_df["그룹"] == g]
            color = color_palette[i % len(color_palette)]

            # 노출수: 왼쪽 Y축, 실선
            fig.add_trace(go.Scatter(
                x=gdf["_x"], y=gdf["노출수"],
                mode="lines+markers",
                name=f"{g} 노출수",
                line=dict(color=color, width=2),
                marker=dict(size=8),
                yaxis="y",
                legendgroup=g,
                hovertemplate="<b>%{x}</b><br>" + g + " 노출수: %{y:,.0f}<extra></extra>",
            ))

            # 클릭수: 오른쪽 Y축, 점선
            fig.add_trace(go.Scatter(
                x=gdf["_x"], y=gdf["클릭수"],
                mode="lines+markers",
                name=f"{g} 클릭수",
                line=dict(color=color, width=2, dash="dot"),
                marker=dict(size=6, symbol="diamond"),
                yaxis="y2",
                legendgroup=g,
                hovertemplate="<b>%{x}</b><br>" + g + " 클릭수: %{y:,.0f}<extra></extra>",
            ))

        fig.update_layout(
            title="👁️ 노출수(실선) · 🖱️ 클릭수(점선) 추이",
            xaxis=dict(
                title="",
                categoryorder="array",
                categoryarray=x_order,
            ),
            yaxis=dict(
                title="노출수",
                side="left",
                showgrid=True,
            ),
            yaxis2=dict(
                title="클릭수",
                side="right",
                overlaying="y",
                showgrid=False,
            ),
            hovermode="x unified",
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True)

    if selected_campaign_id is None:
        st.subheader("🎯 그룹별 성과")
        curr_with_group = curr_data.merge(
            campaigns_df[["캠페인ID", "그룹"]], on="캠페인ID", how="left"
        )
        group_summary = curr_with_group.groupby("그룹").agg(
            캠페인수=("캠페인ID", "count"),
            노출수=("노출수", "sum"),
            클릭수=("클릭수", "sum"),
            전환수=("전환수", "sum"),
            비용=("비용", "sum"),
        ).reset_index()
        if not group_summary.empty:
            group_summary["CTR(%)"] = (
                group_summary["클릭수"] / group_summary["노출수"] * 100
            ).round(2)
            group_summary["CPC"] = (
                group_summary["비용"] / group_summary["클릭수"]
            ).round(0).astype("Int64")
            st.dataframe(group_summary, use_container_width=True)

    st.subheader("🔍 캠페인별 상세")
    campaign_detail = curr_data.merge(
        campaigns_df[["캠페인ID", "캠페인명", "그룹"]], on="캠페인ID", how="left"
    )
    if not campaign_detail.empty:
        if section == "전체":
            campaign_detail = campaign_detail.groupby(
                ["그룹", "캠페인명", "캠페인ID"]
            ).agg(
                노출수=("노출수", "sum"),
                클릭수=("클릭수", "sum"),
                전환수=("전환수", "sum"),
                비용=("비용", "sum"),
            ).reset_index()

        campaign_detail["CTR(%)"] = (
            campaign_detail["클릭수"] / campaign_detail["노출수"] * 100
        ).round(2)
        campaign_detail["CPC"] = (
            campaign_detail["비용"] / campaign_detail["클릭수"]
        ).round(0).astype("Int64")

        display_cols = ["그룹", "캠페인명", "노출수", "클릭수", "전환수", "비용", "CTR(%)", "CPC"]
        st.dataframe(
            campaign_detail[display_cols].sort_values("비용", ascending=False),
            use_container_width=True,
        )

    st.subheader("📌 그룹별 상세 지표")
    curr_metrics = filter_metrics_by_period(metrics_df, year, month, section)
    if selected_group != "전체" and not curr_metrics.empty:
        curr_metrics = curr_metrics[curr_metrics["그룹"] == selected_group]

    if not curr_metrics.empty:
        # 그룹별 지표값 집계
        metric_summary = curr_metrics.groupby(["그룹", "지표종류"])["지표값"].sum().reset_index()

        # Grouped bar chart (그룹×지표별 개별 막대)
        fig_metrics = go.Figure()

        groups_in_metrics = metric_summary["그룹"].unique().tolist()
        metrics_in_data = metric_summary["지표종류"].unique().tolist()

        # 지표별로 trace 추가 (같은 지표는 같은 색)
        metric_palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                         "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]

        for i, metric in enumerate(metrics_in_data):
            metric_data = metric_summary[metric_summary["지표종류"] == metric]
            # 각 그룹별 값 (없는 그룹은 0으로)
            values = []
            for g in groups_in_metrics:
                row = metric_data[metric_data["그룹"] == g]
                values.append(int(row["지표값"].iloc[0]) if not row.empty else 0)

            fig_metrics.add_trace(go.Bar(
                x=groups_in_metrics,
                y=values,
                name=metric,
                marker_color=metric_palette[i % len(metric_palette)],
                text=values,
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>" + metric + ": %{y:,.0f}건<extra></extra>",
            ))

        fig_metrics.update_layout(
            title="",
            xaxis_title="그룹",
            yaxis_title="건수",
            barmode="group",  # 그룹별로 막대를 옆에 나란히
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_metrics, use_container_width=True)
    else:
        st.info("선택한 조건의 그룹지표 데이터가 없습니다.")


# ═══════════════════════════════════════════════════════════
# ➕ 데이터 입력
# ═══════════════════════════════════════════════════════════
elif page == "➕ 데이터 입력":
    if st.session_state.get("user_role") != "admin":
        st.error("🚫 이 페이지에 접근할 권한이 없습니다.")
        st.stop()

    st.header("➕ 캠페인 데이터 입력")

    try:
        campaigns_df = load_campaigns()
        metadata_df = load_metadata()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    active_campaigns = campaigns_df[
        campaigns_df["활성"].astype(str).str.upper() == "TRUE"
    ] if not campaigns_df.empty else pd.DataFrame()

    tab1, tab2 = st.tabs(["📈 캠페인 성과 입력", "🎯 그룹 지표 입력"])

    with tab1:
        st.subheader("캠페인별 데이터 입력")
        st.caption("캠페인을 선택하면 예산·유형·URL은 자동으로 표시됩니다. 성과 데이터만 입력하세요.")

        if active_campaigns.empty:
            st.warning("등록된 활성 캠페인이 없습니다.")
        else:
            campaign_options = {
                f"[{row['캠페인ID']}] {row['캠페인명']} ({row['그룹']})": row['캠페인ID']
                for _, row in active_campaigns.iterrows()
            }
            selected_label = st.selectbox("캠페인 선택", list(campaign_options.keys()))
            selected_id = campaign_options[selected_label]
            selected_row = active_campaigns[active_campaigns["캠페인ID"] == selected_id].iloc[0]

            info_col1, info_col2, info_col3 = st.columns(3)
            info_col1.info(f"**예산**: ₩{int(selected_row['예산']):,}")
            info_col2.info(f"**유형**: {selected_row['유형']}")
            info_col3.info(f"**URL**: {selected_row['URL']}")

            with st.form("form_data", clear_on_submit=True):
                col1, col2 = st.columns(2)
                d_start = col1.date_input("날짜 시작", value=date.today())
                d_end = col2.date_input("날짜 끝", value=date.today())

                col3, col4, col5, col6 = st.columns(4)
                impressions = col3.number_input("노출수", min_value=0, step=1)
                clicks = col4.number_input("클릭수", min_value=0, step=1)
                conversions = col5.number_input("전환수", min_value=0, step=1)
                cost = col6.number_input("비용", min_value=0, step=1000)

                submitted = st.form_submit_button("💾 저장", type="primary")
                if submitted:
                    try:
                        append_data_row({
                            "날짜시작": format_date(d_start),
                            "날짜끝": format_date(d_end),
                            "캠페인ID": selected_id,
                            "노출수": impressions,
                            "클릭수": clicks,
                            "전환수": conversions,
                            "비용": cost,
                        })
                        st.success(f"✅ [{selected_id}] {selected_row['캠페인명']} 저장 완료!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

    with tab2:
        st.subheader("그룹 지표 추가")
        if metadata_df.empty:
            st.warning("metadata 탭에 등록된 지표가 없습니다.")
        else:
            groups_list = metadata_df["그룹"].unique().tolist()
            selected_group_m = st.selectbox("그룹 선택", groups_list, key="metric_group")
            available_metrics = get_metrics_for_group(metadata_df, selected_group_m)

            if not available_metrics:
                st.warning(f"'{selected_group_m}' 그룹에 등록된 지표가 없습니다.")
            else:
                with st.form("form_metrics", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    m_start = col1.date_input("날짜 시작", value=date.today(), key="ms")
                    m_end = col2.date_input("날짜 끝", value=date.today(), key="me")

                    st.write(f"**{selected_group_m}** 그룹의 지표값:")
                    metric_values = {}
                    cols = st.columns(len(available_metrics))
                    for i, m in enumerate(available_metrics):
                        metric_values[m] = cols[i].number_input(
                            m, min_value=0, step=1, key=f"m_{m}"
                        )

                    submitted = st.form_submit_button("💾 저장", type="primary")
                    if submitted:
                        try:
                            for m, v in metric_values.items():
                                append_group_metric({
                                    "날짜시작": format_date(m_start),
                                    "날짜끝": format_date(m_end),
                                    "그룹": selected_group_m,
                                    "지표종류": m,
                                    "지표값": v,
                                })
                            st.success(f"✅ {selected_group_m} 지표 {len(metric_values)}개 저장 완료!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"저장 실패: {e}")


# ═══════════════════════════════════════════════════════════
# 🎯 캠페인 관리
# ═══════════════════════════════════════════════════════════
elif page == "🎯 캠페인 관리":
    if st.session_state.get("user_role") != "admin":
        st.error("🚫 이 페이지에 접근할 권한이 없습니다.")
        st.stop()

    st.header("🎯 캠페인 관리")

    try:
        campaigns_df = load_campaigns()
        groups_df = load_groups()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

    tab1, tab2 = st.tabs(["📋 캠페인 목록", "➕ 새 캠페인 등록"])

    with tab1:
        st.subheader("등록된 캠페인")
        if campaigns_df.empty:
            st.info("등록된 캠페인이 없습니다.")
        else:
            group_filter = st.selectbox(
                "그룹 필터",
                ["전체"] + campaigns_df["그룹"].unique().tolist(),
            )
            display_df = campaigns_df if group_filter == "전체" else \
                campaigns_df[campaigns_df["그룹"] == group_filter]
            st.dataframe(display_df, use_container_width=True)
            st.caption(f"총 {len(display_df)}개 캠페인")

    with tab2:
        st.subheader("새 캠페인 등록")
        if groups_df.empty:
            st.error("groups 탭에 데이터가 없습니다.")
        else:
            group_list = groups_df["그룹"].tolist()
            selected_group_new = st.selectbox("그룹 선택", group_list, key="new_camp_group")
            preview_id = generate_campaign_id(selected_group_new, campaigns_df, groups_df)
            st.info(f"자동 생성될 캠페인ID: **{preview_id}**")

            with st.form("form_new_campaign", clear_on_submit=True):
                campaign_name = st.text_input("캠페인명", placeholder="예: 검색광고_말레이시아")
                col1, col2 = st.columns(2)
                budget = col1.number_input("예산 (₩)", min_value=0, step=10000)
                ad_type = col2.text_input("유형", placeholder="예: 동영상, 검색, 디맨드젠 캠페인")
                url = st.text_input("URL", placeholder="예: en.vlif.co.kr")
                is_active = st.checkbox("활성 상태로 등록", value=True)

                submitted = st.form_submit_button("💾 등록", type="primary")
                if submitted:
                    if not campaign_name:
                        st.error("캠페인명은 필수입니다.")
                    else:
                        try:
                            new_id = generate_campaign_id(selected_group_new, campaigns_df, groups_df)
                            append_campaign_master({
                                "캠페인ID": new_id,
                                "캠페인명": campaign_name,
                                "그룹": selected_group_new,
                                "예산": budget,
                                "유형": ad_type,
                                "URL": url,
                                "활성": "TRUE" if is_active else "FALSE",
                            })
                            st.success(f"✅ [{new_id}] {campaign_name} 등록 완료!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"등록 실패: {e}")


# ═══════════════════════════════════════════════════════════
# 💬 코멘트 관리
# ═══════════════════════════════════════════════════════════
elif page == "💬 코멘트 관리":
    if st.session_state.get("user_role") != "admin":
        st.error("🚫 이 페이지에 접근할 권한이 없습니다.")
        st.stop()

    st.header("💬 기간 코멘트 관리")

    try:
        comments_df = load_comments()
    except Exception as e:
        st.error(f"코멘트 로드 실패: {e}")
        st.stop()

    tab1, tab2 = st.tabs(["📝 새 코멘트 작성", "📋 코멘트 목록"])

    with tab1:
        st.subheader("새 코멘트 작성")

        today = date.today()
        col1, col2, col3 = st.columns([1, 1, 2])
        c_year = col1.selectbox("년도", [2026, 2025], index=0, key="c_year")
        c_month = col2.selectbox(
            "월", list(range(1, 13)),
            index=today.month - 1,
            format_func=lambda m: f"{m}월",
            key="c_month",
        )
        c_section = col3.selectbox(
            "기간",
            ["전체", "상순 (1~10일)", "중순 (11~20일)", "하순 (21~월말)"],
            key="c_section",
        )

        c_section_short = get_section_label(c_section)
        existing = comments_df[
            (comments_df["년도"] == c_year)
            & (comments_df["월"] == c_month)
            & (comments_df["기간"] == c_section_short)
        ] if not comments_df.empty else pd.DataFrame()

        if not existing.empty:
            st.warning(f"⚠️ 이 기간에 이미 {len(existing)}개의 코멘트가 있습니다.")

        with st.form("form_comment", clear_on_submit=True):
            author = st.text_input("작성자", value=st.session_state.user_name)
            comment_text = st.text_area(
                "코멘트 내용",
                placeholder="예: 7월 상순은 영미권과 국내 캠페인 모두 전환 성과가 크게 개선됨...",
                height=200,
            )

            submitted = st.form_submit_button("💾 저장", type="primary")
            if submitted:
                if not comment_text.strip():
                    st.error("코멘트 내용은 필수입니다.")
                else:
                    try:
                        new_id = generate_comment_id(comments_df)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        append_comment({
                            "코멘트ID": new_id,
                            "년도": c_year,
                            "월": c_month,
                            "기간": c_section_short,
                            "코멘트": comment_text.strip(),
                            "작성일시": now_str,
                            "작성자": author or st.session_state.user_name,
                        })
                        st.success(f"✅ 코멘트 저장 완료! (ID: {new_id})")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

    with tab2:
        st.subheader("코멘트 목록")
        if comments_df.empty:
            st.info("작성된 코멘트가 없습니다.")
        else:
            col1, col2, col3 = st.columns(3)
            f_year = col1.selectbox(
                "년도 필터",
                ["전체"] + sorted(comments_df["년도"].dropna().unique().astype(int).tolist(), reverse=True),
                key="f_year",
            )
            f_month = col2.selectbox(
                "월 필터",
                ["전체"] + list(range(1, 13)),
                format_func=lambda x: "전체" if x == "전체" else f"{x}월",
                key="f_month",
            )
            f_section = col3.selectbox(
                "기간 필터",
                ["전체", "상순", "중순", "하순"],
                key="f_section",
            )

            filtered = comments_df.copy()
            if f_year != "전체":
                filtered = filtered[filtered["년도"] == f_year]
            if f_month != "전체":
                filtered = filtered[filtered["월"] == f_month]
            if f_section != "전체":
                filtered = filtered[filtered["기간"] == f_section]

            filtered = filtered.sort_values("작성일시", ascending=False)
            st.caption(f"총 {len(filtered)}개 코멘트")

            for _, row in filtered.iterrows():
                with st.container(border=True):
                    header_col1, header_col2 = st.columns([3, 1])
                    header_col1.markdown(
                        f"**[{row['코멘트ID']}]** {int(row['년도'])}년 {int(row['월'])}월 {row['기간']}"
                    )
                    header_col2.caption(f"_{row['작성일시']}_")
                    st.write(row["코멘트"])
                    st.caption(f"✍️ {row['작성자']}")
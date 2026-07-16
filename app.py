import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import calendar

# ─────────────────────────────────
# 페이지 설정
# ─────────────────────────────────
st.set_page_config(
    page_title="빌리프 광고 대시보드",
    page_icon="📊",
    layout="wide",
)

st.title("📊 빌리프 광고 대시보드")

SHEET_URL = "https://docs.google.com/spreadsheets/d/11CyqrC-4VIwxaiTzJBJjfyxWb8ARlbjBmfAVIZd3KNU/edit"


# ─────────────────────────────────
# 구글 시트 클라이언트
# ─────────────────────────────────
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
    return df


@st.cache_data(ttl=60)
def load_group_metrics():
    df = pd.DataFrame(get_worksheet("group_metrics").get_all_records())
    if not df.empty and "지표값" in df.columns:
        df["지표값"] = pd.to_numeric(df["지표값"], errors="coerce")
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
    """CM001 형식으로 자동 생성."""
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


# ─────────────────────────────────
# 기간 유틸
# ─────────────────────────────────
def get_period_range(year, month, section):
    last_day = calendar.monthrange(year, month)[1]
    if section == "전체":
        return f"{month:02d}/01", f"{month:02d}/{last_day:02d}"
    elif section == "상순 (1~10일)":
        return f"{month:02d}/01", f"{month:02d}/10"
    elif section == "중순 (11~20일)":
        return f"{month:02d}/11", f"{month:02d}/20"
    elif section == "하순 (21~월말)":
        return f"{month:02d}/21", f"{month:02d}/{last_day:02d}"


def get_previous_period(year, month, section):
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    return prev_year, prev_month, section


def _parse_mmdd(s):
    try:
        parts = str(s).strip().split("/")
        if len(parts) != 2:
            return None, None
        return int(parts[0]), int(parts[1])
    except (ValueError, AttributeError):
        return None, None


def filter_data_by_period(data_df, year, month, section):
    if data_df.empty:
        return data_df.iloc[0:0]
    curr_start, curr_end = get_period_range(year, month, section)
    if section == "전체":
        df = data_df.copy()
        df["_start_month"] = df["날짜시작"].apply(lambda x: _parse_mmdd(x)[0])
        return df[df["_start_month"] == month].drop(columns=["_start_month"])
    else:
        return data_df[
            (data_df["날짜시작"] == curr_start) & (data_df["날짜끝"] == curr_end)
        ]


def filter_metrics_by_period(metrics_df, year, month, section):
    if metrics_df.empty:
        return metrics_df.iloc[0:0]
    curr_start, curr_end = get_period_range(year, month, section)
    if section == "전체":
        df = metrics_df.copy()
        df["_start_month"] = df["날짜시작"].apply(lambda x: _parse_mmdd(x)[0])
        return df[df["_start_month"] == month].drop(columns=["_start_month"])
    else:
        return metrics_df[
            (metrics_df["날짜시작"] == curr_start) & (metrics_df["날짜끝"] == curr_end)
        ]


def get_section_label(section):
    """UI에 표시되는 긴 이름을 시트 저장용 짧은 이름으로 변환."""
    mapping = {
        "전체": "전체",
        "상순 (1~10일)": "상순",
        "중순 (11~20일)": "중순",
        "하순 (21~월말)": "하순",
    }
    return mapping.get(section, section)


def section_from_label(label):
    """시트에 저장된 짧은 이름 → UI 긴 이름."""
    mapping = {
        "전체": "전체",
        "상순": "상순 (1~10일)",
        "중순": "중순 (11~20일)",
        "하순": "하순 (21~월말)",
    }
    return mapping.get(label, label)


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
page = st.sidebar.radio("메뉴", [
    "📊 대시보드",
    "➕ 데이터 입력",
    "🎯 캠페인 관리",
    "💬 코멘트 관리",
])


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

    # ─────── 필터 ───────
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

    # ─────── 기간 표시 ───────
    curr_start, curr_end = get_period_range(year, month, section)
    prev_year, prev_month, prev_section = get_previous_period(year, month, section)
    prev_start, prev_end = get_period_range(prev_year, prev_month, prev_section)

    filter_desc = f"**현재**: {year}년 {curr_start} ~ {curr_end}"
    filter_desc += f"  |  **비교**: {prev_year}년 {prev_start} ~ {prev_end}"
    if selected_group != "전체":
        filter_desc += f"  |  **그룹**: {selected_group}"
    if selected_campaign_id:
        filter_desc += f"  |  **캠페인**: {selected_campaign_label}"
    st.caption(filter_desc)

    # ─────── 데이터 필터링 ───────
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

    # ─────── 코멘트 표시 (현재 기간에 대한 코멘트 자동 로드) ───────
    st.subheader("💬 기간 코멘트")
    section_label = get_section_label(section)
    current_comments = comments_df[
        (comments_df["년도"] == year)
        & (comments_df["월"] == month)
        & (comments_df["기간"] == section_label)
    ] if not comments_df.empty else pd.DataFrame()

    if not current_comments.empty:
        # 작성일시 최신순 정렬
        current_comments = current_comments.sort_values("작성일시", ascending=False)
        for _, row in current_comments.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['작성자']}** · _{row['작성일시']}_")
                st.write(row["코멘트"])
    else:
        st.info("이 기간에 대한 코멘트가 아직 없습니다. 💬 코멘트 관리에서 작성할 수 있습니다.")

    # ─────── 요약 카드 ───────
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
        pivot = curr_metrics.pivot_table(
            index="그룹", columns="지표종류", values="지표값",
            aggfunc="sum", fill_value=0,
        )
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("선택한 조건의 그룹지표 데이터가 없습니다.")


# ═══════════════════════════════════════════════════════════
# ➕ 데이터 입력
# ═══════════════════════════════════════════════════════════
elif page == "➕ 데이터 입력":
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
            st.warning("등록된 활성 캠페인이 없습니다. 먼저 '캠페인 관리'에서 캠페인을 등록해주세요.")
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
                            "날짜시작": d_start.strftime("%m/%d"),
                            "날짜끝": d_end.strftime("%m/%d"),
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
                                    "날짜시작": m_start.strftime("%m/%d"),
                                    "날짜끝": m_end.strftime("%m/%d"),
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
                            new_id = generate_campaign_id(
                                selected_group_new, campaigns_df, groups_df
                            )
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
    st.header("💬 기간 코멘트 관리")
    st.caption("특정 기간에 대한 리뷰/인사이트/특이사항 등을 자유롭게 기록합니다.")

    try:
        comments_df = load_comments()
    except Exception as e:
        st.error(f"코멘트 로드 실패: {e}")
        st.stop()

    tab1, tab2 = st.tabs(["📝 새 코멘트 작성", "📋 코멘트 목록"])

    # ─────── 작성 폼 ───────
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

        # 해당 기간에 기존 코멘트 있는지 미리보기
        c_section_short = get_section_label(c_section)
        existing = comments_df[
            (comments_df["년도"] == c_year)
            & (comments_df["월"] == c_month)
            & (comments_df["기간"] == c_section_short)
        ] if not comments_df.empty else pd.DataFrame()

        if not existing.empty:
            st.warning(f"⚠️ 이 기간에 이미 {len(existing)}개의 코멘트가 있습니다. 아래는 새로 추가하는 것입니다.")

        with st.form("form_comment", clear_on_submit=True):
            author = st.text_input("작성자", value="빌리프")
            comment_text = st.text_area(
                "코멘트 내용",
                placeholder="예: 7월 상순은 영미권과 국내 캠페인 모두 전환 성과가 크게 개선됨. 영미권은 CTR 0.47%→0.97%로 약 2배 상승, CPC는 40% 감소...",
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
                            "작성자": author or "빌리프",
                        })
                        st.success(f"✅ 코멘트 저장 완료! (ID: {new_id})")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

    # ─────── 목록 조회 ───────
    with tab2:
        st.subheader("코멘트 목록")
        if comments_df.empty:
            st.info("작성된 코멘트가 없습니다.")
        else:
            # 필터
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
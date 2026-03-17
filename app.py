"""
이커머스 트렌드 분석 툴 - Streamlit 메인
포트폴리오용 범용 트렌드 분석 대시보드
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import yaml
import io
import time

from collectors.naver_api import fetch_all_data, fetch_yoy_comparison, fetch_gender_age_trend, fetch_keyword_trend_batch
from collectors.brand_analyzer import analyze_brand, extract_brand_structured
from collectors.google_trends import fetch_google_trends, merge_naver_google, fetch_google_trending_kr
from ai.insight_engine     import calculate_keyword_stats, detect_hidden_rising, generate_insight


# =============================================
# 페이지 기본 설정
# =============================================

st.set_page_config(
    page_title="이커머스 트렌드 분석 툴",
    page_icon="📊",
    layout="wide",
)


# =============================================
# config.yaml 로드
# =============================================

@st.cache_data
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_config()


# =============================================
# 사이드바 - 수집 설정
# =============================================

st.sidebar.title("⚙️ 수집 설정")

category_options = {v["name"]: k for k, v in config["categories"].items()}
selected_name    = st.sidebar.selectbox("카테고리 선택", list(category_options.keys()))
selected_key     = category_options[selected_name]
selected_config  = config["categories"][selected_key]

top_n = st.sidebar.selectbox(
    "수집 키워드 수",
    options=[20, 50, 100],
    index=2,
    format_func=lambda x: f"Top {x}",
)

period_days = st.sidebar.selectbox(
    "수집 기간",
    options=[30, 60, 90, 180],
    index=2,
    format_func=lambda x: f"최근 {x}일",
)

time_unit = st.sidebar.radio(
    "시간 단위",
    options=["week", "month"],
    format_func=lambda x: "주별" if x == "week" else "월별",
)

st.sidebar.markdown("---")
st.sidebar.subheader("🏢 자사 브랜드 설정 (선택)")
brand_url = st.sidebar.text_input(
    "브랜드 홈페이지 URL",
    placeholder="https://exxxtreme.co.kr/",
    help="입력 시 브랜드 자동 분석 후 AI 인사이트에 반영됩니다",
)
st.sidebar.markdown("---")
collect_button = st.sidebar.button("🔍 데이터 수집 시작", use_container_width=True)

# 브랜드 구조화 데이터 수동 보정 UI
if st.session_state.get("brand_structured") and st.session_state.brand_structured.get("own_keywords"):
    st.sidebar.markdown("---")
    st.sidebar.subheader("✏️ 브랜드 정보 보정")
    st.sidebar.caption("Gemini가 자동 추출한 값입니다. 직접 수정 후 적용하세요.")

    bs = st.session_state.brand_structured

    edited_gender = st.sidebar.selectbox(
        "타겟 성별",
        options = ["전체", "남성", "여성"],
        index   = ["전체", "남성", "여성"].index(bs.get("target_gender", "전체")),
        key     = "edit_gender",
    )

    age_options  = ["10대", "20대", "30대", "40대", "50대이상"]
    edited_ages  = st.sidebar.multiselect(
        "타겟 연령대",
        options  = age_options,
        default  = [a for a in bs.get("target_ages", []) if a in age_options],
        key      = "edit_ages",
    )

    edited_keywords = st.sidebar.text_area(
        "자사 제품/성분 키워드 (쉼표 구분)",
        value   = ", ".join(bs.get("own_keywords", [])),
        height  = 100,
        key     = "edit_keywords",
    )

    if st.sidebar.button("✅ 브랜드 정보 적용", key="btn_apply_brand"):
        kw_list = [k.strip() for k in edited_keywords.split(",") if k.strip()]
        st.session_state.brand_structured = {
            "target_gender": edited_gender,
            "target_ages":   edited_ages,
            "own_keywords":  kw_list,
        }
        st.sidebar.success("적용 완료!")
        st.rerun()


# =============================================
# 메인 화면 - 타이틀
# =============================================

st.title("📊 이커머스 트렌드 분석 툴")
st.caption("네이버 쇼핑인사이트 인기 키워드 자동 수집 | 수치 기반 MD·마케터·운영팀 인사이트")
st.markdown("---")


# =============================================
# 세션 상태 초기화
# =============================================

for key in ["category_df", "keyword_df", "stats_df", "collected_category", "batch_count", "google_df", "merged_df", "google_trending", "yoy_df", "gender_df", "age_df", "brand_context", "brand_name", "brand_structured"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame() if "df" in key else ""
        if key == "batch_count":
            st.session_state[key] = 0
        if key == "google_trending":
            st.session_state[key] = []


# =============================================
# 데이터 수집 실행
# =============================================

if collect_button:
    progress_bar = st.progress(0)
    status_text  = st.empty()

    def update_progress(pct, msg):
        progress_bar.progress(pct)
        status_text.text(msg)

    result = fetch_all_data(
        category_id       = selected_config["naver_category_id"],
        category_name     = selected_name,
        category_config   = selected_config,
        top_n             = top_n,
        days              = period_days,
        time_unit         = time_unit,
        progress_callback = update_progress,
    )

    st.session_state.category_df        = result["category_df"]
    st.session_state.keyword_df         = result["keyword_df"]
    st.session_state.stats_df           = calculate_keyword_stats(result["keyword_df"])
    st.session_state.collected_category = selected_name
    st.session_state.batch_count        = result["batch_count"]

    top_keywords = result["keywords"]

    update_progress(0.7, "API 쿨다운 중... (30초)")
    time.sleep(30)

    # 전년 동기 대비 수집
    if top_keywords:
        update_progress(0.75, "전년 동기 대비 수집 중...")
        st.session_state.yoy_df = fetch_yoy_comparison(
            keywords  = top_keywords,
            days      = period_days,
            time_unit = time_unit,
        )

    update_progress(0.88, "API 쿨다운 중... (30초)")
    time.sleep(30)

    # 구글 트렌드는 버튼 클릭 시 별도 수집 (자동 수집 제외)
    st.session_state.google_df      = pd.DataFrame()
    st.session_state.merged_df      = pd.DataFrame()
    st.session_state.google_trending = []

    # 브랜드 분석
    if brand_url.strip():
        update_progress(0.93, "브랜드 홈페이지 분석 중...")
        brand_result = analyze_brand(brand_url.strip())
        st.session_state.brand_context    = brand_result["context"]
        st.session_state.brand_name       = brand_result["brand_name"]
        # 구조화 데이터 추출
        structured = extract_brand_structured(brand_result["context"])
        st.session_state.brand_structured = structured
        print(f"[INFO] 브랜드 구조화 데이터: {structured}")

    # 성별/연령별 트렌드 수집
    if top_keywords:
        update_progress(0.96, "성별/연령별 트렌드 수집 중... (약 2~3분 소요)")
        ga_result = fetch_gender_age_trend(
            keywords  = top_keywords,
            days      = period_days,
            time_unit = time_unit,
        )
        st.session_state.gender_df = ga_result["gender_df"]
        st.session_state.age_df    = ga_result["age_df"]

    progress_bar.empty()
    status_text.empty()

    kw_count = len(result["keywords"])
    st.success(f"✅ '{selected_name}' 완료 — 키워드 {kw_count}개 / API {result['batch_count']}회 호출")


# =============================================
# 변수 단축
# =============================================

category_df     = st.session_state.category_df
keyword_df      = st.session_state.keyword_df
stats_df        = st.session_state.stats_df
yoy_df          = st.session_state.yoy_df
google_trending = st.session_state.google_trending if st.session_state.google_trending else []


# =============================================
# 카테고리 클릭 트렌드 차트
# =============================================

if not category_df.empty:
    st.subheader(f"📈 {st.session_state.collected_category} 카테고리 클릭 트렌드")

    fig = px.line(
        category_df,
        x="날짜", y="클릭지수",
        markers=True,
        color_discrete_sequence=["#4A90E2"],
    )
    fig.update_layout(xaxis_title="기간", yaxis_title="클릭지수 (상대값)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

# =============================================
# 성별 / 연령별 트렌드 분석
# =============================================

gender_df = st.session_state.gender_df
age_df    = st.session_state.age_df

if not gender_df.empty and not age_df.empty:
    st.subheader("👥 성별 / 연령별 트렌드 분석")
    st.caption("네이버 검색지수 기반 — 성별·연령별 키워드 수요 분포")

    tab_gender, tab_age, tab_cross = st.tabs([
        "⚧ 성별 비교",
        "📅 연령별 비교",
        "🔀 교차 분석",
    ])

    with tab_gender:
        st.caption("키워드별 남성 vs 여성 검색지수 평균 비교 — 높을수록 해당 성별 수요 강함")
        pivot_gender = gender_df.pivot_table(
            index="키워드", columns="성별", values="검색지수", aggfunc="mean"
        ).round(1).reset_index()
        if "남성" in pivot_gender.columns and "여성" in pivot_gender.columns:
            pivot_gender["성별차이"] = (pivot_gender["남성"] - pivot_gender["여성"]).round(1)
            pivot_gender = pivot_gender.sort_values("남성", ascending=False).reset_index(drop=True)

        top20_gender = pivot_gender.head(20)
        fig_gender = px.bar(
            top20_gender.melt(id_vars="키워드", value_vars=["남성", "여성"],
                              var_name="성별", value_name="검색지수"),
            x="키워드", y="검색지수", color="성별",
            barmode="group",
            color_discrete_map={"남성": "#4A90E2", "여성": "#E25C8A"},
            title="Top 20 키워드 성별 검색지수 비교",
        )
        # 타겟 성별 안내
        target_g = st.session_state.get("brand_structured", {}).get("target_gender", "")
        if target_g and target_g != "전체":
            st.info(f"💡 브랜드 타겟 성별: **{target_g}** — 차트에서 {target_g} 막대를 집중해서 확인하세요")
        fig_gender.update_layout(xaxis_tickangle=-45, height=450)
        st.plotly_chart(fig_gender, use_container_width=True)
        st.dataframe(pivot_gender, use_container_width=True, hide_index=True)

    with tab_age:
        st.caption("키워드별 연령대 검색지수 평균 비교 — 어느 연령대가 가장 관심 많은지 확인")
        pivot_age = age_df.pivot_table(
            index="키워드", columns="연령대", values="검색지수", aggfunc="mean"
        ).round(1).reset_index()

        age_order = ["10대", "20대", "30대", "40대", "50대이상"]
        age_cols  = [c for c in age_order if c in pivot_age.columns]

        top20_age = pivot_age.head(20)
        fig_age = px.bar(
            top20_age.melt(id_vars="키워드", value_vars=age_cols,
                           var_name="연령대", value_name="검색지수"),
            x="키워드", y="검색지수", color="연령대",
            barmode="group",
            title="Top 20 키워드 연령대별 검색지수 비교",
        )
        # 타겟 연령 안내
        target_ages = st.session_state.get("brand_structured", {}).get("target_ages", [])
        if target_ages:
            st.info(f"💡 브랜드 타겟 연령대: **{', '.join(target_ages)}** — 해당 연령대를 집중해서 확인하세요")
        fig_age.update_layout(xaxis_tickangle=-45, height=450)
        st.plotly_chart(fig_age, use_container_width=True)
        st.dataframe(pivot_age, use_container_width=True, hide_index=True)

    with tab_cross:
        st.caption("특정 키워드 선택 → 성별+연령 교차 분포 확인")
        all_kw = sorted(gender_df["키워드"].unique().tolist())
        selected_kw = st.selectbox("키워드 선택", all_kw, key="cross_kw_select")

        col1, col2 = st.columns(2)
        with col1:
            g_data = gender_df[gender_df["키워드"] == selected_kw]
            if not g_data.empty:
                fig_g = px.pie(
                    g_data, values="검색지수", names="성별",
                    color_discrete_map={"남성": "#4A90E2", "여성": "#E25C8A"},
                    title=f"{selected_kw} — 성별 분포",
                )
                st.plotly_chart(fig_g, use_container_width=True)

        with col2:
            a_data = age_df[age_df["키워드"] == selected_kw]
            if not a_data.empty:
                a_data = a_data.copy()
                a_data["연령대"] = pd.Categorical(
                    a_data["연령대"], categories=age_order, ordered=True
                )
                a_data = a_data.sort_values("연령대")
                fig_a = px.bar(
                    a_data, x="연령대", y="검색지수",
                    color="연령대",
                    title=f"{selected_kw} — 연령대 분포",
                )
                st.plotly_chart(fig_a, use_container_width=True)

    st.markdown("---")


# =============================================
# 키워드 순위 테이블 + 급상승 차트
# =============================================

if not stats_df.empty:

    # ① 급상승 카드
    rising = detect_hidden_rising(stats_df, threshold_pct=30.0)
    if not rising.empty:
        st.subheader("🚀 급상승 감지 — 이전엔 묻혔다가 지금 뜨는 키워드")
        cols = st.columns(min(len(rising), 4))
        for i, (_, row) in enumerate(rising.head(4).iterrows()):
            with cols[i]:
                st.metric(
                    label = row["키워드"],
                    value = f"지수 {row['최근평균']}",
                    delta = f"+{row['급상승율']}% (초반 대비)",
                )
        st.markdown("---")

    # ② Top 10 트렌드 차트
    st.subheader("📊 검색지수 Top 10 트렌드")
    st.caption("전체 키워드 중 검색지수 상위 10개만 차트로 표시")

    top10_kw = stats_df.head(10)["키워드"].tolist()
    chart_df = keyword_df[keyword_df["키워드"].isin(top10_kw)]

    if not chart_df.empty:
        fig2 = px.line(
            chart_df,
            x="날짜", y="검색지수", color="키워드",
            markers=True,
        )
        fig2.update_layout(xaxis_title="기간", yaxis_title="검색지수 (상대값)", hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    # ③ 전체 키워드 순위 테이블
    st.subheader(f"📋 전체 키워드 순위표 (총 {len(stats_df)}개)")
    st.caption("컬럼 클릭으로 정렬 | 전주대비·3주추이·급상승율 기준으로 정렬해보세요")

    display_cols = ["순위", "키워드", "최신지수", "전주대비", "3주추이", "90일최고", "90일최저", "최고대비", "급상승율"]
    display_df   = stats_df[display_cols].copy()

    # 자사 보유 키워드 강조
    brand_s    = st.session_state.get("brand_structured", {})
    own_kw_set = set(brand_s.get("own_keywords", []))
    if own_kw_set:
        display_df.insert(2, "자사보유", display_df["키워드"].apply(
            lambda x: "✅" if any(ok in x or x in ok for ok in own_kw_set) else ""
        ))

    display_df["급상승율"] = display_df["급상승율"].apply(
        lambda x: f"+{x}%" if pd.notna(x) and x > 0 else ("-" if pd.isna(x) else f"{x}%")
    )

    st.dataframe(
        display_df,
        use_container_width = True,
        height              = 500,
        column_config       = {
            "순위":    st.column_config.NumberColumn("순위",    width="small"),
            "자사보유": st.column_config.TextColumn("자사보유", width="small"),
            "키워드":  st.column_config.TextColumn("키워드",   width="medium"),
            "최신지수": st.column_config.NumberColumn("최신지수", format="%.1f", width="small"),
            "전주대비": st.column_config.TextColumn("전주대비", width="small"),
            "3주추이":  st.column_config.TextColumn("3주추이",  width="medium"),
            "90일최고": st.column_config.NumberColumn("90일최고", format="%.1f", width="small"),
            "90일최저": st.column_config.NumberColumn("90일최저", format="%.1f", width="small"),
            "최고대비": st.column_config.TextColumn("최고대비", width="small"),
            "급상승율": st.column_config.TextColumn("🚀급상승율", width="small"),
        },
        hide_index = True,
    )

    st.markdown("---")

# =============================================
# 전년 동기 대비 (YoY) 시즌 예측
# =============================================

if not yoy_df.empty:
    st.subheader("📅 전년 동기 대비 시즌 예측")
    st.caption("작년 같은 기간 대비 올해 검색량 변화 — 양수(+)면 작년보다 성장, 음수(-)면 하락")

    growing  = yoy_df[yoy_df["YoY증감율"].notna() & (yoy_df["YoY증감율"] > 0)]
    declining = yoy_df[yoy_df["YoY증감율"].notna() & (yoy_df["YoY증감율"] < 0)]
    new_kw   = yoy_df[yoy_df["작년평균"] == 0]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📈 작년 대비 성장", f"{len(growing)}개",
                  help="올해 검색량이 작년 동기보다 높은 키워드")
    with col2:
        st.metric("📉 작년 대비 하락", f"{len(declining)}개",
                  help="올해 검색량이 작년 동기보다 낮은 키워드")
    with col3:
        st.metric("🆕 신규 키워드", f"{len(new_kw)}개",
                  help="작년에는 없었고 올해 새로 뜨는 키워드")

    st.markdown("---")

    tab_grow, tab_new, tab_all, tab_chart = st.tabs([
        "📈 성장 키워드",
        "🆕 신규 키워드",
        "📋 전체 비교표",
        "📊 YoY 차트",
    ])

    with tab_grow:
        st.caption("작년 동기 대비 성장률 상위 키워드 — 올해 특히 뜨고 있는 시즌 키워드")
        grow_display = growing.head(20).copy()
        grow_display["YoY증감율"] = grow_display["YoY증감율"].apply(lambda x: f"+{x}%")
        st.dataframe(
            grow_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "키워드":    st.column_config.TextColumn("키워드",      width="medium"),
                "올해평균":  st.column_config.NumberColumn("올해 평균", format="%.1f",
                    help="올해 같은 기간 검색지수 평균"),
                "작년평균":  st.column_config.NumberColumn("작년 평균", format="%.1f",
                    help="작년 같은 기간 검색지수 평균"),
                "YoY증감율": st.column_config.TextColumn("📈 YoY 증감율", width="small"),
            },
        )

    with tab_new:
        st.caption("작년에는 없었고 올해 새로 등장한 키워드 — 신규 트렌드 선점 기회")
        if not new_kw.empty:
            st.dataframe(
                new_kw[["키워드", "올해평균"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "키워드":   st.column_config.TextColumn("키워드",     width="medium"),
                    "올해평균": st.column_config.NumberColumn("올해 평균", format="%.1f"),
                },
            )
        else:
            st.info("신규 키워드가 없습니다.")

    with tab_all:
        st.caption("전체 키워드 올해 vs 작년 비교")
        all_display = yoy_df.copy()
        all_display["YoY증감율"] = all_display["YoY증감율"].apply(
            lambda x: f"+{x}%" if pd.notna(x) and x > 0 else ("-" if pd.isna(x) else f"{x}%")
        )
        st.dataframe(
            all_display,
            use_container_width=True,
            height=500,
            hide_index=True,
            column_config={
                "키워드":    st.column_config.TextColumn("키워드",      width="medium"),
                "올해평균":  st.column_config.NumberColumn("올해 평균", format="%.1f"),
                "작년평균":  st.column_config.NumberColumn("작년 평균", format="%.1f"),
                "YoY증감율": st.column_config.TextColumn("YoY 증감율", width="small"),
            },
        )

    with tab_chart:
        st.caption("YoY 증감율 상위/하위 10개 — 올해 뜨는 것 vs 식는 것")
        chart_data = yoy_df[yoy_df["YoY증감율"].notna()].copy()
        top10_grow = chart_data.nlargest(10, "YoY증감율")
        top10_drop = chart_data.nsmallest(10, "YoY증감율")
        chart_yoy  = pd.concat([top10_grow, top10_drop]).drop_duplicates()

        if not chart_yoy.empty:
            chart_yoy["색상"] = chart_yoy["YoY증감율"].apply(
                lambda x: "성장" if x > 0 else "하락"
            )
            fig_yoy = px.bar(
                chart_yoy.sort_values("YoY증감율"),
                x="YoY증감율", y="키워드",
                orientation="h",
                color="색상",
                color_discrete_map={"성장": "#4A90E2", "하락": "#E25C4A"},
                labels={"YoY증감율": "전년 동기 대비 (%)"},
            )
            fig_yoy.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
            st.plotly_chart(fig_yoy, use_container_width=True)

    st.markdown("---")

# =============================================
# 추가 키워드 수집
# =============================================

if not stats_df.empty:
    st.subheader("🔍 키워드 추가 조회")
    st.caption("현재 수집 목록에 없는 키워드를 추가로 조회해서 순위표에 합산합니다")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        extra_kw = st.text_input(
            "키워드 입력",
            placeholder="예) 아르기닌, 마카 (쉼표로 여러 개 입력 가능)",
            label_visibility="collapsed",
            key="extra_kw_input",
        )
    with col_btn:
        btn_extra = st.button("➕ 추가 수집", key="btn_extra_kw")

    if btn_extra and extra_kw.strip():
        extra_list = [k.strip() for k in extra_kw.split(",") if k.strip()]
        with st.spinner(f"{extra_list} 수집 중..."):
            # 네이버 트렌드 수집
            extra_trend_df = fetch_keyword_trend_batch(
                keywords  = extra_list,
                days      = period_days,
                time_unit = time_unit,
            )
            if not extra_trend_df.empty:
                # 기존 keyword_df에 합산
                combined_kw = pd.concat(
                    [st.session_state.keyword_df, extra_trend_df],
                    ignore_index=True
                ).drop_duplicates(subset=["날짜", "키워드"])
                st.session_state.keyword_df = combined_kw

                # stats_df 재계산
                from ai.insight_engine import calculate_keyword_stats
                st.session_state.stats_df = calculate_keyword_stats(combined_kw)

                # YoY 추가 수집
                extra_yoy = fetch_yoy_comparison(
                    keywords  = extra_list,
                    days      = period_days,
                    time_unit = time_unit,
                )
                if not extra_yoy.empty and not st.session_state.yoy_df.empty:
                    st.session_state.yoy_df = pd.concat(
                        [st.session_state.yoy_df, extra_yoy],
                        ignore_index=True
                    ).drop_duplicates(subset=["키워드"])

                # 성별/연령 추가 수집
                if not st.session_state.gender_df.empty:
                    extra_ga = fetch_gender_age_trend(
                        keywords  = extra_list,
                        days      = period_days,
                        time_unit = time_unit,
                    )
                    st.session_state.gender_df = pd.concat(
                        [st.session_state.gender_df, extra_ga["gender_df"]],
                        ignore_index=True
                    ).drop_duplicates(subset=["키워드", "성별"])
                    st.session_state.age_df = pd.concat(
                        [st.session_state.age_df, extra_ga["age_df"]],
                        ignore_index=True
                    ).drop_duplicates(subset=["키워드", "연령대"])

                st.success(f"✅ {extra_list} 추가 완료! 전체 지표에 반영됐어요.")
                st.rerun()
            else:
                st.warning("데이터를 가져오지 못했어요. 키워드를 확인해주세요.")

    st.markdown("---")


# =============================================
# 구글 트렌드 비교
# =============================================

merged_df = st.session_state.merged_df
google_df = st.session_state.google_df

if not stats_df.empty:
    st.subheader("🌐 네이버 + 구글 동시 트렌드 분석")
    st.caption("양쪽 플랫폼에서 동시에 뜨는 키워드 = 진짜 트렌드 신호")

    if st.button("🔍 구글 트렌드 수집 시작 (약 2~3분 소요)", key="btn_google_trends"):
        with st.spinner("구글 트렌드 수집 중... 잠시만 기다려주세요"):
            top_kw = stats_df["키워드"].tolist()
            google_df_new = fetch_google_trends(top_kw, days=period_days)
            st.session_state.google_df  = google_df_new
            st.session_state.merged_df  = merge_naver_google(
                naver_keywords = top_kw,
                google_df      = google_df_new,
                naver_df       = keyword_df,
            )
            st.rerun()

merged_df = st.session_state.merged_df
google_df = st.session_state.google_df

if not merged_df.empty:

    both_df    = merged_df[merged_df["동시트렌드"] == True].reset_index(drop=True)
    naver_only = merged_df[merged_df["구글_평균"] < 30].reset_index(drop=True)

    naver_kw_set   = set(merged_df["키워드"].tolist())
    google_only_kw = [kw for kw in google_trending if kw not in naver_kw_set]
    google_only_df = pd.DataFrame({"구글_급상승_키워드": google_only_kw}) if google_only_kw else pd.DataFrame()

    def to_grade(score):
        if score >= 80: return "🏆 S"
        elif score >= 60: return "🟢 A"
        elif score >= 40: return "🟡 B"
        elif score >= 20: return "🟠 C"
        else: return "🔴 D"

    def trend_comment(row):
        if row["동시트렌드"] and row["트렌드점수"] >= 70:
            return "🔥 양쪽 모두 강하게 상승 중"
        elif row["동시트렌드"]:
            return "✅ 양쪽 동시 상승"
        elif row["네이버_평균"] >= 50:
            return "🟠 국내 한정 강세"
        else:
            return "📉 신호 약함"

    merged_display = merged_df.copy()
    merged_display["등급"] = merged_display["트렌드점수"].apply(to_grade)
    merged_display["상태"] = merged_display.apply(trend_comment, axis=1)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("✅ 양쪽 동시 트렌드", f"{len(both_df)}개",
                  help="네이버 + 구글 양쪽에서 모두 검색지수가 높은 키워드")
    with col2:
        st.metric("🟠 네이버만 상승", f"{len(naver_only)}개",
                  help="네이버에선 뜨지만 구글 관심도 30 미만 — 국내 한정 트렌드")

    st.markdown("---")

    tab_both, tab_naver, tab_chart = st.tabs([
        "✅ 동시 트렌드 키워드",
        "🟠 네이버 단독 키워드",
        "📊 트렌드 점수 차트",
    ])

    with tab_both:
        st.caption("네이버 + 구글 양쪽 모두 상승 중 — 가장 강력한 트렌드 신호")
        if not both_df.empty:
            both_display = merged_display[merged_display["동시트렌드"] == True][
                ["키워드", "등급", "네이버_평균", "구글_평균", "구글_최신", "트렌드점수", "상태"]
            ].reset_index(drop=True)
            st.dataframe(
                both_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "키워드":     st.column_config.TextColumn("키워드",  width="medium"),
                    "등급":       st.column_config.TextColumn("등급",    width="small"),
                    "네이버_평균": st.column_config.NumberColumn("네이버 평균", format="%.1f",
                        help="네이버 검색지수 평균 (0~100, 높을수록 검색 많음)"),
                    "구글_평균":  st.column_config.NumberColumn("구글 평균", format="%.1f",
                        help="구글 트렌드 관심도 평균 (0~100, 상대적 관심도)"),
                    "구글_최신":  st.column_config.NumberColumn("구글 최신", format="%d",
                        help="구글 트렌드 가장 최근 시점 관심도"),
                    "트렌드점수": st.column_config.NumberColumn("🔥 트렌드점수", format="%.1f",
                        help="네이버+구글 합산 점수 (100점 만점)"),
                    "상태":       st.column_config.TextColumn("상태",    width="medium"),
                },
            )
        else:
            st.info("동시 트렌드 키워드가 없습니다.")

    with tab_naver:
        st.caption("네이버에선 뜨지만 구글에선 미미한 키워드 — 국내 한정 트렌드")
        if not naver_only.empty:
            naver_display = merged_display[merged_display["구글_평균"] < 30][
                ["키워드", "등급", "네이버_평균", "구글_평균", "트렌드점수", "상태"]
            ].reset_index(drop=True)
            st.dataframe(
                naver_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "키워드":     st.column_config.TextColumn("키워드",  width="medium"),
                    "등급":       st.column_config.TextColumn("등급",    width="small"),
                    "네이버_평균": st.column_config.NumberColumn("네이버 평균", format="%.1f",
                        help="네이버 검색지수 평균 (0~100)"),
                    "구글_평균":  st.column_config.NumberColumn("구글 평균",  format="%.1f",
                        help="30 미만 = 구글에서 관심 낮음"),
                    "트렌드점수": st.column_config.NumberColumn("트렌드점수", format="%.1f"),
                    "상태":       st.column_config.TextColumn("상태",    width="medium"),
                },
            )
        else:
            st.info("해당 키워드가 없습니다.")

    with tab_chart:
        st.caption("트렌드 점수 기준 상위 20개 — S/A/B/C/D 등급 색상 구분")
        top20 = merged_display.head(20)
        if not top20.empty:
            fig_g = px.bar(
                top20,
                x="트렌드점수", y="키워드",
                orientation="h",
                color="동시트렌드",
                color_discrete_map={True: "#4A90E2", False: "#F5A623"},
                hover_data=["등급", "상태", "네이버_평균", "구글_평균"],
                labels={"동시트렌드": "동시트렌드"},
            )
            fig_g.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
            st.plotly_chart(fig_g, use_container_width=True)

    st.markdown("---")

# =============================================
# AI 인사이트 탭 (맨 마지막 배치)
# =============================================

if not stats_df.empty:
    st.subheader("🤖 AI 인사이트 (직무별)")
    st.caption("수집된 수치 기반 — 모든 결론에 검색지수·전주대비·3주추이 수치가 인용됩니다")

    tab_md, tab_marketer, tab_ops = st.tabs(["🛒 MD 관점", "📢 마케터 관점", "⚙️ 운영팀 관점"])

    with tab_md:
        if st.button("MD 인사이트 생성", key="btn_md"):
            with st.spinner("MD 관점 인사이트 생성 중..."):
                insight = generate_insight(
                    category_df   = category_df,
                    stats_df      = stats_df,
                    category_name = st.session_state.collected_category,
                    job_type      = "MD",
                    merged_df     = st.session_state.merged_df,
                    brand_context = st.session_state.get("brand_context", ""),
                )
                st.session_state["insight_md"] = insight
        if st.session_state.get("insight_md"):
            st.markdown(st.session_state["insight_md"])
            st.markdown("---")
            st.caption("💬 MD 관점으로 추가 질문하기")
            md_custom = st.text_area("추가 질문 입력", placeholder="예) 이 중에서 30대 여성 타겟으로 발주 우선순위 다시 뽑아줘", key="md_custom_input", label_visibility="collapsed")
            if st.button("MD 추가 질문 전송", key="btn_md_custom"):
                if md_custom.strip():
                    with st.spinner("추가 질문 처리 중..."):
                        custom_result = generate_insight(
                            category_df   = category_df,
                            stats_df      = stats_df,
                            category_name = st.session_state.collected_category,
                            job_type      = "MD",
                            merged_df     = st.session_state.merged_df,
                            custom_prompt = md_custom,
                        )
                        st.markdown(custom_result)

    with tab_marketer:
        if st.button("마케터 인사이트 생성", key="btn_marketer"):
            with st.spinner("마케터 관점 인사이트 생성 중..."):
                insight = generate_insight(
                    category_df   = category_df,
                    stats_df      = stats_df,
                    category_name = st.session_state.collected_category,
                    job_type      = "마케터",
                    merged_df     = st.session_state.merged_df,
                )
                st.session_state["insight_marketer"] = insight
        if st.session_state.get("insight_marketer"):
            st.markdown(st.session_state["insight_marketer"])
            st.markdown("---")
            st.caption("💬 마케터 관점으로 추가 질문하기")
            mk_custom = st.text_area("추가 질문 입력", placeholder="예) 이번 주 SNS 콘텐츠 기획안 3개 뽑아줘", key="mk_custom_input", label_visibility="collapsed")
            if st.button("마케터 추가 질문 전송", key="btn_mk_custom"):
                if mk_custom.strip():
                    with st.spinner("추가 질문 처리 중..."):
                        custom_result = generate_insight(
                            category_df   = category_df,
                            stats_df      = stats_df,
                            category_name = st.session_state.collected_category,
                            job_type      = "마케터",
                            merged_df     = st.session_state.merged_df,
                            custom_prompt = mk_custom,
                        )
                        st.markdown(custom_result)

    with tab_ops:
        if st.button("운영팀 인사이트 생성", key="btn_ops"):
            with st.spinner("운영팀 관점 인사이트 생성 중..."):
                insight = generate_insight(
                    category_df   = category_df,
                    stats_df      = stats_df,
                    category_name = st.session_state.collected_category,
                    job_type      = "운영팀",
                    merged_df     = st.session_state.merged_df,
                )
                st.session_state["insight_ops"] = insight
        if st.session_state.get("insight_ops"):
            st.markdown(st.session_state["insight_ops"])
            st.markdown("---")
            st.caption("💬 운영팀 관점으로 추가 질문하기")
            ops_custom = st.text_area("추가 질문 입력", placeholder="예) 이번 주 상단 노출 우선순위 5개만 뽑아줘", key="ops_custom_input", label_visibility="collapsed")
            if st.button("운영팀 추가 질문 전송", key="btn_ops_custom"):
                if ops_custom.strip():
                    with st.spinner("추가 질문 처리 중..."):
                        custom_result = generate_insight(
                            category_df   = category_df,
                            stats_df      = stats_df,
                            category_name = st.session_state.collected_category,
                            job_type      = "운영팀",
                            merged_df     = st.session_state.merged_df,
                            custom_prompt = ops_custom,
                        )
                        st.markdown(custom_result)

    st.markdown("---")

    # 공통 자유 질문
    st.subheader("💬 데이터 기반 자유 질문")
    st.caption("직무 관계없이 수집된 데이터를 기반으로 자유롭게 질문하세요")
    free_prompt = st.text_area("질문을 입력하세요", placeholder="예) 지금 데이터에서 가장 위험한 신호 3가지만 짚어줘", key="free_prompt_input")
    if st.button("🔍 질문 전송", key="btn_free"):
        if free_prompt.strip():
            with st.spinner("답변 생성 중..."):
                free_result = generate_insight(
                    category_df   = category_df,
                    stats_df      = stats_df,
                    category_name = st.session_state.collected_category,
                    job_type      = "MD",
                    merged_df     = st.session_state.merged_df,
                    custom_prompt = free_prompt,
                )
                st.markdown(free_result)

    st.markdown("---")

# =============================================
# 엑셀 다운로드
# =============================================

if not stats_df.empty:
    st.subheader("📥 데이터 다운로드")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if not category_df.empty:
            category_df.to_excel(writer, sheet_name="카테고리_트렌드", index=False)
        stats_df.to_excel(writer, sheet_name="키워드_순위", index=False)
        if not keyword_df.empty:
            keyword_df.to_excel(writer, sheet_name="키워드_전체트렌드", index=False)
        if not yoy_df.empty:
            yoy_df.to_excel(writer, sheet_name="전년동기대비_YoY", index=False)
        if not merged_df.empty:
            merged_df.to_excel(writer, sheet_name="네이버_구글_비교", index=False)
        if not gender_df.empty:
            gender_df.to_excel(writer, sheet_name="성별_트렌드", index=False)
        if not age_df.empty:
            age_df.to_excel(writer, sheet_name="연령별_트렌드", index=False)

    st.download_button(
        label     = "📥 엑셀 다운로드",
        data      = output.getvalue(),
        file_name = f"trend_{st.session_state.collected_category}.xlsx",
        mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

else:
    st.info("👈 왼쪽 사이드바에서 카테고리를 선택하고 '데이터 수집 시작' 버튼을 눌러주세요.")
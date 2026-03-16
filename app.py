"""
이커머스 트렌드 분석 툴 - Streamlit 메인
포트폴리오용 범용 트렌드 분석 대시보드
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import yaml
import io

from collectors.naver_api import fetch_all_data
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
    options=[30, 60, 90],
    index=2,
    format_func=lambda x: f"최근 {x}일",
)

time_unit = st.sidebar.radio(
    "시간 단위",
    options=["week", "month"],
    format_func=lambda x: "주별" if x == "week" else "월별",
)

st.sidebar.markdown("---")
collect_button = st.sidebar.button("🔍 데이터 수집 시작", use_container_width=True)


# =============================================
# 메인 화면 - 타이틀
# =============================================

st.title("📊 이커머스 트렌드 분석 툴")
st.caption("네이버 쇼핑인사이트 인기 키워드 자동 수집 | 수치 기반 MD·마케터·운영팀 인사이트")
st.markdown("---")


# =============================================
# 세션 상태 초기화
# =============================================

for key in ["category_df", "keyword_df", "stats_df", "collected_category", "batch_count", "google_df", "merged_df", "google_trending"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame() if "df" in key else ""
        if key == "batch_count":
            st.session_state[key] = 0


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

    # 구글 트렌드 수집 (네이버 상위 50개 기준)
    top_keywords = result["keywords"]
    if top_keywords:
        update_progress(0.85, "구글 트렌드 수집 중...")
        google_df = fetch_google_trends(top_keywords, days=period_days)
        st.session_state.google_df  = google_df
        st.session_state.merged_df  = merge_naver_google(
            naver_keywords = top_keywords,
            google_df      = google_df,
            naver_df       = result["keyword_df"],
        )
        update_progress(0.95, "구글 급상승 키워드 수집 중...")
        st.session_state.google_trending = fetch_google_trending_kr()

    progress_bar.empty()
    status_text.empty()

    kw_count = len(result["keywords"])
    st.success(f"✅ '{selected_name}' 완료 — 키워드 {kw_count}개 / API {result['batch_count']}회 호출")


# =============================================
# 변수 단축
# =============================================

category_df      = st.session_state.category_df
keyword_df       = st.session_state.keyword_df
stats_df         = st.session_state.stats_df
google_trending  = st.session_state.google_trending if st.session_state.google_trending else []


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

    # ② Top 10 트렌드 차트 (차트는 상위 10개만 — 가독성 유지)
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

    display_df["급상승율"] = display_df["급상승율"].apply(
        lambda x: f"+{x}%" if pd.notna(x) and x > 0 else ("-" if pd.isna(x) else f"{x}%")
    )

    st.dataframe(
        display_df,
        use_container_width = True,
        height              = 500,
        column_config       = {
            "순위":    st.column_config.NumberColumn("순위",    width="small"),
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
# AI 인사이트 탭
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
                )
                st.markdown(insight)

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
                st.markdown(insight)

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
                st.markdown(insight)

    st.markdown("---")


# =============================================
# 구글 트렌드 비교
# =============================================

merged_df = st.session_state.merged_df
google_df = st.session_state.google_df

if not merged_df.empty:
    st.subheader("🌐 네이버 + 구글 동시 트렌드 분석")
    st.caption("양쪽 플랫폼에서 동시에 뜨는 키워드 = 진짜 트렌드 신호")

    both_df    = merged_df[merged_df["동시트렌드"] == True].reset_index(drop=True)
    naver_only = merged_df[merged_df["구글_평균"] < 30].reset_index(drop=True)

    # 구글 자체 급상승 중 네이버 상위 키워드에 없는 것
    naver_kw_set   = set(merged_df["키워드"].tolist())
    google_only_kw = [kw for kw in google_trending if kw not in naver_kw_set]
    google_only_df = pd.DataFrame({"구글_급상승_키워드": google_only_kw}) if google_only_kw else pd.DataFrame()

    # 등급 변환 함수
    def to_grade(score):
        if score >= 80: return "🏆 S"
        elif score >= 60: return "🟢 A"
        elif score >= 40: return "🟡 B"
        elif score >= 20: return "🟠 C"
        else: return "🔴 D"

    # 한줄 코멘트
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
    merged_display["등급"]     = merged_display["트렌드점수"].apply(to_grade)
    merged_display["상태"]     = merged_display.apply(trend_comment, axis=1)

    # 요약 카드
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("✅ 양쪽 동시 트렌드", f"{len(both_df)}개",
                  help="네이버 + 구글 양쪽에서 모두 검색지수가 높은 키워드")
    with col2:
        st.metric("🟠 네이버만 상승", f"{len(naver_only)}개",
                  help="네이버에선 뜨지만 구글 관심도 30 미만 — 국내 한정 트렌드")
    with col3:
        st.metric("🔵 구글 급상승 (네이버 미포함)", f"{len(google_only_kw)}개",
                  help="구글 코리아 실시간 급상승 키워드 중 네이버 수집 목록에 없는 키워드")

    st.markdown("---")

    tab_both, tab_naver, tab_google, tab_chart = st.tabs([
        "✅ 동시 트렌드 키워드",
        "🟠 네이버 단독 키워드",
        "🔵 구글 급상승 키워드",
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
                    "네이버_평균": st.column_config.NumberColumn("네이버 평균",
                        format="%.1f",
                        help="네이버 검색지수 평균 (0~100, 높을수록 검색 많음)"),
                    "구글_평균":  st.column_config.NumberColumn("구글 평균",
                        format="%.1f",
                        help="구글 트렌드 관심도 평균 (0~100, 상대적 관심도)"),
                    "구글_최신":  st.column_config.NumberColumn("구글 최신",
                        format="%d",
                        help="구글 트렌드 가장 최근 시점 관심도"),
                    "트렌드점수": st.column_config.NumberColumn("🔥 트렌드점수",
                        format="%.1f",
                        help="네이버+구글 합산 점수 (100점 만점, 높을수록 양쪽 모두 강한 트렌드)"),
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

    with tab_google:
        st.caption("구글 코리아 실시간 급상승 키워드 중 네이버 수집 목록에 없는 키워드 — 선제적 트렌드 포착 가능")
        if not google_only_df.empty:
            st.dataframe(google_only_df, use_container_width=True, hide_index=True)
        else:
            st.info("구글 급상승 키워드 수집에 실패했거나 모두 네이버와 겹칩니다.")

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
        if not merged_df.empty:
            merged_df.to_excel(writer, sheet_name="네이버_구글_비교", index=False)

    st.download_button(
        label     = "📥 엑셀 다운로드",
        data      = output.getvalue(),
        file_name = f"trend_{st.session_state.collected_category}.xlsx",
        mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

else:
    st.info("👈 왼쪽 사이드바에서 카테고리를 선택하고 '데이터 수집 시작' 버튼을 눌러주세요.")
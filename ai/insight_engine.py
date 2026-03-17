"""
AI 인사이트 엔진
- Gemini API 연결
- 직무별 프롬프트 분기 (MD / 마케터 / 운영팀)
- 수치 근거 자동 계산 (전주대비, 3주추이, 90일최고/최저, 급상승 감지)
"""

from google import genai
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# =============================================
# 수치 계산 함수
# =============================================

def calculate_keyword_stats(keyword_df: pd.DataFrame) -> pd.DataFrame:
    if keyword_df.empty:
        return pd.DataFrame()

    rows = []
    for kw, group in keyword_df.groupby("키워드"):
        group  = group.sort_values("날짜").reset_index(drop=True)
        values = group["검색지수"].tolist()

        if not values:
            continue

        latest_val  = values[-1]
        prev_val    = values[-2] if len(values) >= 2 else None
        max_val     = max(values)
        min_val     = min(values)

        if prev_val and prev_val != 0:
            change_pct = round((latest_val - prev_val) / prev_val * 100, 1)
            change_str = f"+{change_pct}%" if change_pct > 0 else f"{change_pct}%"
        else:
            change_pct = None
            change_str = "-"

        if len(values) >= 3:
            v3 = values[-3:]
            if v3[-1] > v3[-2] > v3[-3]:
                trend_3w = "📈 3주연속상승"
            elif v3[-1] < v3[-2] < v3[-3]:
                trend_3w = "📉 3주연속하락"
            elif v3[-1] > v3[-2]:
                trend_3w = "↗ 반등"
            elif v3[-1] < v3[-2]:
                trend_3w = "↘ 조정"
            else:
                trend_3w = "→ 보합"
        else:
            trend_3w = "-"

        vs_peak = round((latest_val - max_val) / max_val * 100, 1) if max_val != 0 else 0
        vs_peak_str = f"{vs_peak}%" if vs_peak != 0 else "최고점"

        early_avg  = round(sum(values[:4]) / 4, 2) if len(values) >= 4 else None
        recent_avg = round(sum(values[-2:]) / 2, 2) if len(values) >= 2 else None
        if early_avg and early_avg != 0 and recent_avg:
            rise_pct = round((recent_avg - early_avg) / early_avg * 100, 1)
        else:
            rise_pct = None

        rows.append({
            "키워드":     kw,
            "최신지수":   round(latest_val, 1),
            "전주대비":   change_str,
            "전주대비수치": change_pct,
            "3주추이":    trend_3w,
            "90일최고":   round(max_val, 1),
            "90일최저":   round(min_val, 1),
            "최고대비":   vs_peak_str,
            "초반평균":   early_avg,
            "최근평균":   recent_avg,
            "급상승율":   rise_pct,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("최신지수", ascending=False).reset_index(drop=True)
        df.insert(0, "순위", range(1, len(df) + 1))

    return df


def detect_hidden_rising(stats_df: pd.DataFrame, threshold_pct: float = 30.0) -> pd.DataFrame:
    if stats_df.empty or "급상승율" not in stats_df.columns:
        return pd.DataFrame()

    rising = stats_df[
        stats_df["급상승율"].notna() & (stats_df["급상승율"] >= threshold_pct)
    ].copy()

    return rising.sort_values("급상승율", ascending=False).reset_index(drop=True)


def build_data_summary(
    category_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    category_name: str,
) -> str:
    """AI에 넘길 데이터 요약 — 풍부한 수치 근거 포함"""
    lines = [f"[카테고리: {category_name}]", "[분석 기간: 최근 90일 / 주별 데이터]", ""]

    if not category_df.empty:
        vals   = category_df.sort_values("날짜")["클릭지수"].tolist()
        dates  = category_df.sort_values("날짜")["날짜"].tolist()
        latest = vals[-1]
        prev   = vals[-2] if len(vals) >= 2 else None
        chg    = round((latest - prev) / prev * 100, 1) if prev and prev != 0 else None
        chg_s  = f"+{chg}%" if chg and chg > 0 else (f"{chg}%" if chg else "-")

        lines.append("■ 카테고리 전체 클릭 트렌드")
        lines.append(f"  최신 클릭지수: {round(latest,1)}  ({dates[-1]})")
        lines.append(f"  전주 대비: {chg_s}")
        lines.append(f"  90일 최고: {round(max(vals),1)} / 90일 최저: {round(min(vals),1)}")
        if len(vals) >= 3:
            v3 = vals[-3:]
            if v3[-1] > v3[-2] > v3[-3]:
                lines.append("  3주 추이: 3주 연속 상승 ▲")
            elif v3[-1] < v3[-2] < v3[-3]:
                lines.append("  3주 추이: 3주 연속 하락 ▼")
            else:
                lines.append("  3주 추이: 혼조")
        lines.append("")

    if stats_df.empty:
        lines.append("※ 키워드 트렌드 데이터 없음")
        return "\n".join(lines)

    top20 = stats_df.head(20)
    lines.append("■ 검색지수 Top 20 키워드")
    lines.append(f"  {'순위':>3} {'키워드':<16} {'최신지수':>6} {'전주대비':>8} {'3주추이':<14} {'90일최고':>7} {'최고대비':>7}")
    lines.append(f"  {'-'*70}")
    for _, row in top20.iterrows():
        lines.append(
            f"  {int(row['순위']):>3} "
            f"{str(row['키워드']):<16} "
            f"{row['최신지수']:>6.1f} "
            f"{row['전주대비']:>8} "
            f"{str(row['3주추이']):<14} "
            f"{row['90일최고']:>7.1f} "
            f"{str(row['최고대비']):>7}"
        )
    lines.append("")

    rising3w = stats_df[stats_df["3주추이"].str.contains("3주연속상승", na=False)]
    if not rising3w.empty:
        lines.append("■ 3주 연속 상승 키워드 (트렌드 지속성 신호)")
        for _, row in rising3w.iterrows():
            lines.append(
                f"  - {row['키워드']}: 최신지수 {row['최신지수']} / 전주대비 {row['전주대비']} / 90일최고 {row['90일최고']}"
            )
        lines.append("")

    rising = detect_hidden_rising(stats_df, threshold_pct=30.0)
    lines.append("■ 숨은 급상승 키워드 (초반4주 평균 대비 최근2주 평균 +30% 이상)")
    if not rising.empty:
        for _, row in rising.iterrows():
            lines.append(
                f"  🚀 {row['키워드']}: "
                f"초반평균 {row['초반평균']} → 최근평균 {row['최근평균']} "
                f"(+{row['급상승율']}%) / 현재순위 {int(row['순위'])}위"
            )
    else:
        lines.append("  이번 주기 급상승 키워드 없음 (기준: +30%)")
    lines.append("")

    if "전주대비수치" in stats_df.columns:
        drop_kw = stats_df[
            stats_df["전주대비수치"].notna() & (stats_df["전주대비수치"] <= -20)
        ].head(10)
        if not drop_kw.empty:
            lines.append("■ 급락 키워드 (전주 대비 -20% 이하 — 재고 과잉 위험)")
            for _, row in drop_kw.iterrows():
                lines.append(
                    f"  ⚠️ {row['키워드']}: 최신지수 {row['최신지수']} / 전주대비 {row['전주대비']}"
                )
            lines.append("")

    return "\n".join(lines)


def build_google_summary(merged_df: pd.DataFrame) -> str:
    """네이버+구글 비교 데이터 요약"""
    if merged_df is None or merged_df.empty:
        return ""

    lines = ["■ 네이버+구글 동시 트렌드 비교 (트렌드점수 = 네이버+구글 합산 100점 만점)"]

    both  = merged_df[merged_df["동시트렌드"] == True].head(10)
    naver = merged_df[merged_df["구글_평균"] < 30].head(5)

    if not both.empty:
        lines.append("  [양쪽 동시 상승 — 가장 강력한 트렌드 신호]")
        for _, row in both.iterrows():
            lines.append(
                f"  ✅ {row['키워드']}: 트렌드점수 {row['트렌드점수']} "
                f"(네이버평균 {row['네이버_평균']} / 구글평균 {row['구글_평균']})"
            )
        lines.append("")

    if not naver.empty:
        lines.append("  [네이버 단독 강세 — 국내 한정 트렌드]")
        for _, row in naver.iterrows():
            lines.append(
                f"  🟠 {row['키워드']}: 네이버평균 {row['네이버_평균']} / 구글평균 {row['구글_평균']}"
            )
        lines.append("")

    return "\n".join(lines)


# =============================================
# 직무별 프롬프트 템플릿
# =============================================

PROMPTS = {
    "MD": """
당신은 10년 경력의 이커머스 MD입니다.
아래 데이터는 네이버 검색 트렌드 기반으로 수집된 시장 수요 신호입니다.

[핵심 전제]
- 이 키워드들은 소비자가 실제로 찾고 있는 수요 신호이며, 회사가 현재 판매 중인 제품과 다를 수 있습니다.
- 발주·재고 판단은 금지입니다. 대신 제품 개발 기회, 라인업 확장, 광고 집행 우선순위에 집중하세요.
- 모든 결론에 반드시 수치 근거를 괄호로 명시하세요: (검색지수 91, 전주 +15%, 3주연속상승)
- 예측 성과는 반드시 근거 로직과 함께 제시하세요.

[분석 데이터]
{data_summary}

[출력 형식 — 반드시 이 구조로]

## 📊 시장 수요 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%) | 분석 키워드 수 [N]개

| 지표 | 내용 |
|---|---|
| 수요 1위 | [키워드] — 지수 [수치], 전주 [%], [3주추이] |
| 수요 2위 | [키워드] — 지수 [수치], 전주 [%], [3주추이] |
| 수요 3위 | [키워드] — 지수 [수치], 전주 [%], [3주추이] |
| 3주 연속 상승 | [키워드] — 지속 수요 신호 |
| 급락 주의 | [키워드] — 시장 관심 이탈 신호 |

---

## 🔍 시장 수요 vs 라인업 갭 분석
> 검색 트렌드 상위 키워드 중 현재 라인업에 없을 가능성이 높은 항목을 먼저 식별하세요

| 키워드 | 수요 강도 | 갭 판단 | MD 기회 |
|---|---|---|---|
| [키워드] | 지수 [수치], 전주 [%] | 라인업 부재 가능성 높음/낮음 | [신규개발/라인확장/기존강화] |

---

## 🚀 제품 개발 / 라인업 확장 기회

| 우선순위 | 키워드 | 수요 근거 | 개발 방향 | 예측 성과 |
|---|---|---|---|---|
| 1 | [키워드] | 지수 [수치], 전주 [%], [추이] | [성분 강화/신규 SKU/포맷 변경] | 출시 후 3개월 내 검색 유입 [X]% 기대 (근거: 현재 지수 [수치], 3주 연속 상승 추세) |

---

## 🌐 네이버+구글 동시 트렌드 — 글로벌 수요 확인

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | MD 판단 |
|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | 글로벌 수요 확인 → [신규개발 우선/광고 병행] |

---

## 📢 광고 집행 우선순위 (기존 라인업 대상)

| 순위 | 키워드 | 검색지수 | 전주대비 | 추천 광고 유형 | 예측 성과 |
|---|---|---|---|---|---|
| 1 | [키워드] | [수치] | [%] | [검색광고/배너/SNS] | CTR [X]% 기대 (근거: 지수 [수치], 3주 상승 지속으로 클릭 의향 높음) |

---

## ⚠️ 수요 이탈 키워드 — 기존 제품 개선 신호

| 키워드 | 최신지수 | 전주대비 | 해석 | 제품 개선 방향 |
|---|---|---|---|---|
| [키워드] | [수치] | [%] | 소비자 관심 이탈 | [성분 리뉴얼/패키지 변경/광고 중단] |

---

## 🎯 이번 주 MD 액션 3가지 + 예측 성과
1. **[키워드] 제품 개발 착수 검토** — 근거: (지수 [수치], 전주 [%], [추이]) → 예측: 개발 완료 후 해당 키워드 검색 유입 월 [X]건 기대
2. **[키워드] 광고 집행 강화** — 근거: (지수 [수치], 3주 연속 상승) → 예측: 광고 집행 시 ROAS [X] 이상 기대 (시장 수요 상승 구간)
3. **[키워드] 제품 리뉴얼 검토** — 근거: (지수 [수치], 전주 [%] 하락) → 예측: 리뉴얼 미진행 시 향후 [X]주 내 추가 수요 이탈 우려
""",

    "마케터": """
당신은 이커머스 마케팅 전문가입니다.
아래 데이터는 네이버 검색 트렌드 기반 시장 수요 신호입니다.

[핵심 전제]
- 이 키워드들은 소비자 실수요 신호이며, 자사 제품과 직접 연결되지 않을 수 있습니다.
- 없는 제품은 콘텐츠로 선점하고, 있는 제품은 광고로 전환하는 전략을 제시하세요.
- 모든 결론에 수치 근거를 괄호로 명시하세요.
- 예측 성과는 반드시 근거 로직과 함께 제시하세요.

[분석 데이터]
{data_summary}

[출력 형식]

## 📊 시장 수요 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%)

| 지표 | 내용 |
|---|---|
| 수요 1위 | [키워드] — 지수 [수치] |
| 급상승 | [키워드] — 초반[수치] → 최근[수치] (+[%]) |
| 수요 이탈 | [키워드] — 지수 [수치], 전주 [%] |

---

## 🌐 네이버+구글 동시 트렌드 — 광고 집행 우선순위
> 양쪽 모두 뜨는 키워드 = 광고 ROI 극대화 구간

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | 집행 전략 | 예측 성과 |
|---|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | [검색광고/SNS/콘텐츠] | CTR [X]% / ROAS [X] 기대 (근거: 양쪽 동시 상승 = 수요 확실성 높음) |

---

## ✍️ 콘텐츠 선점 전략 (자사 제품 유무 무관)

| 키워드 | 상승율 | 현재지수 | 콘텐츠 방향 | 예측 효과 |
|---|---|---|---|---|
| [키워드] | +[%] | [수치] | [블로그SEO/숏폼/유튜브] | 콘텐츠 발행 후 [X]주 내 검색 노출 [X]건 기대 |

> 💡 자사 제품이 없는 키워드도 콘텐츠로 선점하면 브랜드 인지도 확보 + 제품 출시 시 즉시 전환 가능

---

## 📢 광고 집행 추천 키워드 Top 5

| 순위 | 키워드 | 검색지수 | 전주대비 | 집행 유형 | 예측 성과 |
|---|---|---|---|---|---|
| 1 | [키워드] | [수치] | [%] | [검색광고/배너] | 월 클릭 [X]건, CVR [X]% 기대 (근거: 지수 [수치], [추이]) |

---

## 📉 예산 축소 키워드

| 키워드 | 최신지수 | 전주대비 | 축소 근거 | 예산 재배분 방향 |
|---|---|---|---|---|
| [키워드] | [수치] | [%] | 수요 이탈 신호 | → [급상승 키워드명]으로 이동 |

---

## ✅ 이번 주 마케터 액션 3가지 + 예측 성과
1. **[키워드] 검색광고 집행** — 근거: (지수 [수치], 전주 +[%]) → 예측: 주간 클릭 [X]건, ROAS [X] 기대
2. **[키워드] 콘텐츠 선점** — 근거: (급상승율 +[%], 현재 [N]위) → 예측: [X]주 내 검색 상위 노출 가능
3. **[키워드] 광고 예산 축소** — 근거: (지수 [수치], 전주 -[%]) → 예측: 예산 [X]% 절감 후 효율 개선
""",

    "운영팀": """
당신은 이커머스 운영 전문가입니다.
아래 데이터는 네이버 검색 트렌드 기반 시장 수요 신호입니다.

[핵심 전제]
- 이 키워드들은 소비자 실수요 신호이며, 자사 판매 제품과 다를 수 있습니다.
- 판매 중인 제품은 노출 최적화, 없는 제품은 페이지 구성 및 MD 전달 우선으로 접근하세요.
- 모든 결론에 수치 근거를 괄호로 명시하세요.
- 예측 성과는 반드시 근거 로직과 함께 제시하세요.

[분석 데이터]
{data_summary}

[출력 형식]

## 📊 시장 수요 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%)

---

## 🌐 네이버+구글 동시 트렌드 — 페이지 노출 최우선

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | 운영 조치 | 예측 효과 |
|---|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | 상단 노출 즉시 적용 | 노출 후 클릭률 [X]% 기대 (근거: 양쪽 동시 상승 = 전환 의향 높음) |

---

## 🚨 이상 수요 감지 (전주 대비 ±20% 이상)

| 키워드 | 최신지수 | 변화율 | 판단 | 운영 대응 | 예측 리스크 |
|---|---|---|---|---|---|
| [키워드] | [수치] | [%] | 급등/급락 | [노출강화/페이지정비] | 미대응 시 [X]주 내 기회 손실 or 재고 리스크 |

---

## 🚀 급상승 키워드 — 즉시 노출 조정 필요

| 키워드 | 초반평균 | 최근평균 | 상승율 | 운영 조치 | 예측 효과 |
|---|---|---|---|---|---|
| [키워드] | [수치] | [수치] | +[%] | 상단 배치 + 기획전 검토 | 노출 강화 시 전환 [X]% 증가 기대 |

---

## 📋 MD 전달 필요 수요 신호
> 자사 판매 제품 없음 또는 라인업 부재로 판단되는 키워드 — MD팀에 즉시 공유

| 키워드 | 수요 강도 | 전달 사유 | 긴급도 |
|---|---|---|---|
| [키워드] | 지수 [수치], 전주 [%] | 검색 수요 있으나 판매 페이지 부재 | 높음/중간 |

---

## ✅ 이번 주 운영팀 액션 3가지 + 예측 성과
1. **[키워드] 상단 노출 즉시 설정** — 근거: (지수 [수치], 전주 +[%]) → 예측: 노출 후 주간 클릭 [X]% 증가
2. **[키워드] MD팀 수요 공유** — 근거: (급상승율 +[%], 판매 페이지 부재) → 예측: 제품 출시 시 초기 검색 유입 즉시 확보
3. **[키워드] 기획전 페이지 구성** — 근거: (지수 [수치], 3주 연속 상승) → 예측: 기획전 오픈 후 [X]주 내 트래픽 [X]% 증가

---

## 🔁 다음 주 모니터링 리스트
| 키워드 | 모니터링 이유 | 기준 수치 | 대응 기준 |
|---|---|---|---|
| [키워드] | [이유] | [수치] | [수치] 초과 시 즉시 노출 강화 |
""",
}


def generate_insight(
    category_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    category_name: str,
    job_type: str = "MD",
    merged_df: pd.DataFrame = None,
    custom_prompt: str = "",
    brand_context: str = "",
) -> str:
    """직무별 AI 인사이트 생성"""
    data_summary   = build_data_summary(category_df, stats_df, category_name)
    google_summary = build_google_summary(merged_df)

    if google_summary:
        data_summary = data_summary + "\n\n" + google_summary

    # 브랜드 컨텍스트 주입
    brand_section = ""
    if brand_context.strip():
        brand_section = f"""
[자사 브랜드 정보 — 반드시 이 정보를 기반으로 라인업 갭 분석 및 인사이트를 작성하세요]
{brand_context}

[중요 지침]
- 트렌드 키워드 중 위 브랜드 제품 라인업에 있는 것과 없는 것을 반드시 구분하세요
- 없는 제품은 신규 개발 또는 콘텐츠 선점 기회로 분류하세요
- 있는 제품은 광고 집행 또는 제품 개선 관점으로 분류하세요
"""

    if custom_prompt.strip():
        prompt = f"""아래 데이터를 참고해서 질문에 답해주세요.
반드시 데이터의 수치를 직접 인용해서 답변하세요.
{brand_section}

[분석 데이터]
{data_summary}

[질문]
{custom_prompt}"""
    else:
        base_prompt = PROMPTS.get(job_type, PROMPTS["MD"]).format(data_summary=data_summary)
        prompt = brand_section + "\n\n" + base_prompt if brand_section else base_prompt

    try:
        response = client.models.generate_content(
            model    = "gemini-2.5-flash",
            contents = prompt,
        )
        return response.text
    except Exception as e:
        return f"[오류] AI 인사이트 생성 실패: {e}"
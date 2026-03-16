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
아래 데이터를 기반으로 소싱·발주·재고 의사결정 인사이트를 작성하세요.
반드시 모든 결론에 아래 데이터의 수치를 직접 인용하세요.
코디·스타일링·계절 설명은 절대 금지입니다.

[분석 데이터]
{data_summary}

[작성 규칙]
- 모든 판단 뒤에 괄호로 수치 근거 명시: (검색지수 91, 전주 +15%, 3주연속상승)
- 숫자 없는 문장은 작성 금지
- 결론은 반드시 발주추천 / 보류 / 제외 중 하나

[출력 형식 — 반드시 이 구조로]

## 📊 핵심 수치 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%) | 분석 키워드 수 [N]개

| 지표 | 내용 |
|---|---|
| 검색 1위 | [키워드] — 지수 [수치], 전주 [증감율]%, [3주추이] |
| 검색 2위 | [키워드] — 지수 [수치], 전주 [증감율]%, [3주추이] |
| 검색 3위 | [키워드] — 지수 [수치], 전주 [증감율]%, [3주추이] |
| 3주연속 상승 | [키워드 목록] |
| 급락 주의 | [키워드 목록] |

---

## 🌐 네이버+구글 동시 트렌드 시그널
> 양쪽 플랫폼 모두에서 뜨는 키워드 = 글로벌+국내 동시 수요

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | MD 판단 |
|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | [즉시발주/관심유지] |

---

## 🚀 숨은 급상승 키워드 — 지금 선점해야 할 시그널

| 키워드 | 초반평균 | 최근평균 | 상승율 | 현재순위 | MD 판단 |
|---|---|---|---|---|---|
| [키워드] | [수치] | [수치] | +[X]% | [N]위 | [즉시발주/관심유지] |

---

## 🛒 발주 우선순위 판단

| 순위 | 키워드 | 검색지수 | 전주대비 | 3주추이 | 발주규모 | 근거 |
|---|---|---|---|---|---|---|
| 1 | [키워드] | [수치] | [%] | [추이] | 대량/중량/소량 | [수치 근거] |

---

## ⚠️ 재고 리스크 키워드

| 키워드 | 최신지수 | 전주대비 | 리스크 수준 | 대응 |
|---|---|---|---|---|
| [키워드] | [수치] | [%] | 높음/중간 | [축소/보류] |

---

## 🎯 이번 주 MD 액션 3가지
1. **[키워드]** 즉시 발주 — 근거: (지수 [수치], 전주 [%], [추이])
2. **[키워드]** 급상승 모니터링 — 근거: (초반[수치] → 최근[수치], +[%])
3. **[키워드]** 재고 축소 검토 — 근거: (지수 [수치], 전주 [%])
""",

    "마케터": """
당신은 이커머스 마케팅 전문가입니다.
아래 데이터를 기반으로 콘텐츠·광고·키워드 전략 인사이트를 작성하세요.
반드시 모든 결론에 수치를 직접 인용하세요.

[분석 데이터]
{data_summary}

[출력 형식]

## 📊 핵심 수치 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%)

| 지표 | 내용 |
|---|---|
| 검색량 1위 | [키워드] — 지수 [수치] |
| 급상승 | [키워드] — 초반[수치] → 최근[수치] (+[%]) |
| 급락 주의 | [키워드] — 지수 [수치], 전주 [%] |

---

## 🌐 네이버+구글 동시 트렌드 — 광고 집행 우선순위
> 양쪽 모두 뜨는 키워드는 광고 ROI가 높을 가능성

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | 집행 전략 |
|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | [검색광고/콘텐츠/SNS] |

---

## 🚀 콘텐츠 선점 기회 키워드

| 키워드 | 상승율 | 현재지수 | 선점 전략 |
|---|---|---|---|
| [키워드] | +[%] | [수치] | [광고/콘텐츠/SEO] |

---

## 📢 이번 주 집행 추천 키워드 Top 5

| 순위 | 키워드 | 검색지수 | 전주대비 | 집행 이유 |
|---|---|---|---|---|
| 1 | [키워드] | [수치] | [%] | [수치 근거] |

---

## ✅ 이번 주 마케터 액션 3가지
1. **[키워드]** 광고 집행 — 근거: (지수 [수치], 전주 +[%])
2. **[키워드]** 콘텐츠 선점 — 근거: (급상승율 +[%], 현재 [N]위)
3. **[키워드]** 예산 축소 — 근거: (지수 [수치], 전주 -[%])
""",

    "운영팀": """
당신은 이커머스 운영 전문가입니다.
아래 데이터를 기반으로 운영 관점의 인사이트를 작성하세요.
반드시 모든 결론에 수치를 직접 인용하세요.

[분석 데이터]
{data_summary}

[출력 형식]

## 📊 핵심 수치 브리핑
> 카테고리 클릭지수 [수치] (전주 [증감율]%)

---

## 🌐 네이버+구글 동시 트렌드 — 페이지 노출 우선순위
> 양쪽 모두 뜨는 키워드는 노출 상단 배치 우선

| 키워드 | 트렌드점수 | 네이버평균 | 구글평균 | 조치 |
|---|---|---|---|---|
| [키워드] | [점수] | [수치] | [수치] | 상단노출 추천 |

---

## 🚨 이상 트렌드 감지 (전주 대비 ±20% 이상)

| 키워드 | 최신지수 | 변화율 | 판단 | 대응 |
|---|---|---|---|---|
| [키워드] | [수치] | [%] | 급등/급락 | [노출조정/재고확인] |

---

## 🚀 급상승 키워드 — 페이지 노출 우선순위 조정 필요

| 키워드 | 초반평균 | 최근평균 | 상승율 | 조치 |
|---|---|---|---|---|
| [키워드] | [수치] | [수치] | +[%] | 상단 노출 추천 |

---

## ✅ 이번 주 운영팀 액션 3가지
1. **[키워드]** 상단 노출 설정 — 근거: (지수 [수치], 전주 +[%])
2. **[키워드]** 재고 점검 — 근거: (급상승율 +[%])
3. **[키워드]** 노출 축소 — 근거: (지수 [수치], 전주 -[%])

---

## 🔁 다음 주 모니터링 리스트
| 키워드 | 모니터링 이유 | 기준 수치 |
|---|---|---|
| [키워드] | [이유] | [수치 이상/이하 시 대응] |
""",
}


def generate_insight(
    category_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    category_name: str,
    job_type: str = "MD",
    merged_df: pd.DataFrame = None,
) -> str:
    """직무별 AI 인사이트 생성"""
    data_summary   = build_data_summary(category_df, stats_df, category_name)
    google_summary = build_google_summary(merged_df)

    if google_summary:
        data_summary = data_summary + "\n\n" + google_summary

    prompt = PROMPTS.get(job_type, PROMPTS["MD"]).format(data_summary=data_summary)

    try:
        response = client.models.generate_content(
            model    = "gemini-2.0-flash",
            contents = prompt,
        )
        return response.text
    except Exception as e:
        return f"[오류] AI 인사이트 생성 실패: {e}"
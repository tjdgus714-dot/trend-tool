"""
구글 트렌드 수집 모듈
- 네이버 키워드 기준으로 구글 트렌드 조회
- 5개씩 배치 처리 + 429 자동 재시도
"""

from pytrends_modern import TrendReq
import pandas as pd
import time


def fetch_google_trends(
    keywords: list,
    days: int = 90,
    progress_callback=None,
) -> pd.DataFrame:
    """
    키워드 리스트를 5개씩 나눠서 구글 트렌드 조회
    429 발생 시 자동 대기 후 재시도
    반환: 키워드별 평균 관심도 DataFrame
    """
    if not keywords:
        return pd.DataFrame()

    # 키워드 전처리
    clean_keywords = []
    for kw in keywords:
        kw = str(kw).strip()
        if kw and len(kw) <= 100:
            clean_keywords.append(kw)

    if not clean_keywords:
        return pd.DataFrame()

    pytrends = TrendReq(hl='ko-KR', tz=540, timeout=(10, 25))

    if days <= 30:
        timeframe = 'today 1-m'
    elif days <= 60:
        timeframe = 'today 2-m'
    elif days <= 90:
        timeframe = 'today 3-m'
    else:
        timeframe = 'today 6-m'

    # 5개씩 배치 (100개 → 20번 호출로 줄임)
    batches  = [clean_keywords[i:i+5] for i in range(0, len(clean_keywords), 5)]
    all_rows = []
    total    = len(batches)

    for idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(idx / total, f"구글 트렌드 수집 중... ({idx+1}/{total})")

        # 429 발생 시 최대 3회 재시도 (대기 30초 → 60초 → 90초)
        for attempt in range(3):
            try:
                pytrends.build_payload(batch, timeframe=timeframe, geo='KR', cat=0)
                df = pytrends.interest_over_time()

                if df.empty:
                    break

                if 'isPartial' in df.columns:
                    df = df.drop(columns=['isPartial'])

                for kw in batch:
                    if kw in df.columns:
                        avg    = round(df[kw].mean(), 1)
                        recent = int(df[kw].iloc[-1])
                        all_rows.append({
                            '키워드':    kw,
                            '구글_평균': avg,
                            '구글_최신': recent,
                        })
                break  # 성공 시 재시도 루프 탈출

            except Exception as e:
                err = str(e)
                if '429' in err:
                    wait = 30 * (attempt + 1)
                    print(f"[WARN] 구글 429 차단 — {wait}초 대기 후 재시도 ({attempt+1}/3)")
                    time.sleep(wait)
                else:
                    print(f"[WARN] 구글 트렌드 배치 실패: {e}")
                    break

        time.sleep(6.0)  # 배치 간 기본 대기 (429 방지 — 20배치 기준 약 2분 소요)

    return pd.DataFrame(all_rows)


def merge_naver_google(
    naver_keywords: list,
    google_df: pd.DataFrame,
    naver_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    네이버 + 구글 데이터 합치기
    반환: 교집합 분석 DataFrame
    """
    if google_df.empty or naver_df.empty:
        return pd.DataFrame()

    naver_latest = (
        naver_df.groupby('키워드')['검색지수']
        .mean()
        .round(1)
        .reset_index()
        .rename(columns={'검색지수': '네이버_평균'})
    )

    merged = pd.merge(naver_latest, google_df, on='키워드', how='inner')

    if merged.empty:
        return pd.DataFrame()

    naver_median     = merged['네이버_평균'].median()
    merged['동시트렌드'] = (
        (merged['네이버_평균'] >= naver_median) &
        (merged['구글_평균']   >= 30)
    )

    merged['트렌드점수'] = (
        (merged['네이버_평균'] / merged['네이버_평균'].max() * 50) +
        (merged['구글_평균']   / 100 * 50)
    ).round(1)

    return merged.sort_values('트렌드점수', ascending=False).reset_index(drop=True)


def fetch_google_trending_kr() -> list:
    """
    구글 코리아 실시간 급상승 키워드 수집
    (엔드포인트 변경으로 현재 비활성화)
    """
    return []
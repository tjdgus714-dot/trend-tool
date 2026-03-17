"""
네이버 쇼핑인사이트 API 수집 모듈
- 카테고리 인기 키워드 Top 100 자동 수집
- 5개씩 루프 돌려서 전체 트렌드 수집
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import configparser
import yaml

load_dotenv()

NAVER_CLIENT_ID      = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET  = os.getenv("NAVER_CLIENT_SECRET")
NAVER_AD_API_KEY     = os.getenv("NAVER_AD_API_KEY", "").strip()
NAVER_AD_SECRET_KEY  = os.getenv("NAVER_AD_SECRET_KEY", "").strip()
NAVER_AD_CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID", "").strip()

HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    "Content-Type":          "application/json",
}

# naver_search_ad 는 import 전에 naver.ini 가 있어야 함
_ini_path = os.path.join(os.getcwd(), "naver.ini")
_cfg = configparser.ConfigParser()
_cfg["DEFAULT"] = {
    "CUSTOMER_ID": f"'{NAVER_AD_CUSTOMER_ID}'",
    "API_KEY":     f"'{NAVER_AD_API_KEY}'",
    "SECRET_KEY":  f"'{NAVER_AD_SECRET_KEY}'",
}
with open(_ini_path, "w") as _f:
    _cfg.write(_f)
print(f"[DEBUG] naver.ini 생성 위치: {_ini_path}")

def get_date_range(days: int = 90) -> tuple:
    """오늘 기준으로 수집 기간 자동 계산"""
    end_date   = datetime.today()
    start_date = end_date - timedelta(days=days)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def fetch_category_keywords(
    category_id: str,
    top_n: int = 500,
) -> list:
    """
    네이버 데이터랩 쇼핑인사이트 인기검색어 크롤링
    쿠키 기반 — 최대 500개 수집 (25페이지 x 20개)
    """
    # config.yaml에서 쿠키 로드
    try:
        with open("config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cookie = cfg.get("datalab_cookie", "")
    except Exception:
        cookie = ""

    if not cookie:
        print("[WARN] config.yaml에 datalab_cookie 없음 — 크롤링 스킵")
        return []

    headers = {
        'User-Agent':       'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        'Referer':          'https://datalab.naver.com/shoppingInsight/sCategory.naver',
        'Content-Type':     'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin':           'https://datalab.naver.com',
        'Cookie':           cookie,
    }

    url        = 'https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver'
    start_date, end_date = get_date_range(30)
    all_keywords = []

    for page in range(1, 26):
        if len(all_keywords) >= top_n:
            break

        data = {
            'cid':       category_id,
            'timeUnit':  'date',
            'startDate': start_date,
            'endDate':   end_date,
            'age':       '',
            'gender':    '',
            'device':    '',
            'page':      str(page),
            'count':     '20',
        }

        try:
            r = requests.post(url, data=data, headers=headers, timeout=10)
            ranks = r.json().get('ranks', [])
            if not ranks:
                break
            all_keywords.extend([item['keyword'] for item in ranks])
        except Exception as e:
            print(f"[WARN] 크롤링 실패 page {page}: {e}")
            break

        time.sleep(0.3)

    print(f"[INFO] 데이터랩 크롤링 완료: {len(all_keywords)}개")
    return all_keywords[:top_n]

def fetch_keyword_trend_batch(
    keywords: list,
    days: int = 90,
    time_unit: str = "week",
) -> pd.DataFrame:
    """
    키워드 리스트를 5개씩 나눠서 루프 — 전체 트렌드 수집
    반환: 전체 키워드 트렌드 DataFrame
    """
    url = "https://openapi.naver.com/v1/datalab/search"
    start_date, end_date = get_date_range(days)

    all_rows   = []
    batch_size = 5
    batches    = [keywords[i:i+batch_size] for i in range(0, len(keywords), batch_size)]

    for batch_idx, batch in enumerate(batches):
        keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in batch]

        body = {
            "startDate":     start_date,
            "endDate":       end_date,
            "timeUnit":      time_unit,
            "keywordGroups": keyword_groups,
            "device":        "",
            "gender":        "",
            "ages":          [],
        }

        try:
            response = requests.post(url, json=body, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                kw_name = result["title"]
                for item in result.get("data", []):
                    all_rows.append({
                        "날짜":    item["period"],
                        "키워드":  kw_name,
                        "검색지수": item["ratio"],
                    })

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] 배치 {batch_idx+1} 수집 실패: {e}")

        # API 과호출 방지 — 배치 사이 0.3초 대기
        time.sleep(0.3)

    df = pd.DataFrame(all_rows)
    if not df.empty:
        last_date = df["날짜"].max()
        df = df[df["날짜"] < last_date].reset_index(drop=True)
    return df


def fetch_shopping_insight(
    category_id: str,
    category_name: str,
    days: int = 90,
    time_unit: str = "week",
) -> pd.DataFrame:
    """네이버 쇼핑인사이트 - 카테고리별 클릭 트렌드 수집"""
    url = "https://openapi.naver.com/v1/datalab/shopping/categories"
    start_date, end_date = get_date_range(days)

    body = {
        "startDate": start_date,
        "endDate":   end_date,
        "timeUnit":  time_unit,
        "category": [
            {
                "name":  category_name,
                "param": [category_id],
            }
        ],
        "device": "",
        "gender": "",
        "ages":   [],
    }

    try:
        response = requests.post(url, json=body, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        rows = []
        for result in data.get("results", []):
            for item in result.get("data", []):
                rows.append({
                    "날짜":     item["period"],
                    "카테고리": category_name,
                    "클릭지수": item["ratio"],
                })

        df = pd.DataFrame(rows)
        if not df.empty:
            last_date = df["날짜"].max()
            df = df[df["날짜"] < last_date].reset_index(drop=True)
        return df

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 쇼핑인사이트 수집 실패: {e}")
        return pd.DataFrame()


def fetch_all_data(
    category_id: str,
    category_name: str,
    category_config: dict,
    top_n: int = 100,
    days: int = 90,
    time_unit: str = "week",
    progress_callback=None,
) -> dict:
    """
    전체 수집 파이프라인
    1) 카테고리 클릭 트렌드
    2) 인기 키워드 Top N 자동 수집
    3) 키워드 트렌드 배치 수집 (5개씩 루프)

    반환: {
        "category_df":  DataFrame,   # 카테고리 클릭 트렌드
        "keyword_df":   DataFrame,   # 전체 키워드 트렌드
        "keywords":     list,        # 수집된 키워드 목록
        "batch_count":  int,         # 실제 API 호출 횟수
    }
    """
    if progress_callback:
        progress_callback(0.1, "카테고리 트렌드 수집 중...")

    category_df = fetch_shopping_insight(
        category_id   = category_id,
        category_name = category_name,
        days          = days,
        time_unit     = time_unit,
    )

    if progress_callback:
        progress_callback(0.3, "인기 키워드 수집 중 (데이터랩 크롤링)...")

    keywords = fetch_category_keywords(
        category_id = category_id,
        top_n       = top_n,
    )

    if not keywords:
        print("[WARN] 크롤링 실패 — config.yaml 키워드로 폴백")
        keywords = (
            category_config.get("category_keywords", []) +
            category_config.get("material_keywords", []) +
            category_config.get("fit_keywords", [])
        )
        print(f"[INFO] config.yaml 폴백 키워드: {len(keywords)}개")

    if not keywords:
        print("[ERROR] 키워드 없음 — 수집 중단")
        return {
            "category_df": category_df,
            "keyword_df":  pd.DataFrame(),
            "keywords":    [],
            "batch_count": 0,
        }

    batch_count = (len(keywords) + 4) // 5

    if progress_callback:
        progress_callback(0.5, "API 쿨다운 중... (30초)")

    import time as _time
    _time.sleep(30)

    if progress_callback:
        progress_callback(0.55, f"키워드 트렌드 수집 중... (총 {batch_count}번 API 호출)")

    keyword_df = fetch_keyword_trend_batch(
        keywords  = keywords,
        days      = days,
        time_unit = time_unit,
    )

    print("[INFO] 기본 수집 완료 — 네이버 API 쿨다운 30초 대기 중...")
    if progress_callback:
        progress_callback(0.65, "네이버 API 쿨다운 중... (30초)")
    time.sleep(30)

    if progress_callback:
        progress_callback(1.0, "수집 완료!")

    return {
        "category_df": category_df,
        "keyword_df":  keyword_df,
        "keywords":    keywords,
        "batch_count": batch_count,
    }

def fetch_yoy_comparison(
    keywords: list,
    days: int = 90,
    time_unit: str = "week",
) -> pd.DataFrame:
    """
    전년 동기 대비 비교
    올해 vs 작년 같은 기간 키워드 트렌드 수집
    반환: 키워드별 올해평균/작년평균/YoY증감율 DataFrame
    """
    url = "https://openapi.naver.com/v1/datalab/search"

    # 올해 기간
    end_this   = datetime.today()
    start_this = end_this - timedelta(days=days)

    # 작년 같은 기간
    end_last   = end_this - timedelta(days=365)
    start_last = start_this - timedelta(days=365)

    results = {}

    for label, start_date, end_date in [
        ("올해", start_this.strftime("%Y-%m-%d"), end_this.strftime("%Y-%m-%d")),
        ("작년", start_last.strftime("%Y-%m-%d"), end_last.strftime("%Y-%m-%d")),
    ]:
        batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]

        for batch in batches:
            keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in batch]
            body = {
                "startDate":     start_date,
                "endDate":       end_date,
                "timeUnit":      time_unit,
                "keywordGroups": keyword_groups,
                "device":        "",
                "gender":        "",
                "ages":          [],
            }

            try:
                r = requests.post(url, json=body, headers=HEADERS, timeout=10)
                r.raise_for_status()
                data = r.json()

                for result in data.get("results", []):
                    kw = result["title"]
                    vals = [item["ratio"] for item in result.get("data", [])]
                    avg = round(sum(vals) / len(vals), 1) if vals else 0
                    if kw not in results:
                        results[kw] = {}
                    results[kw][label] = avg

            except Exception as e:
                print(f"[WARN] YoY 배치 실패: {e}")

            time.sleep(1.0)

    rows = []
    for kw, vals in results.items():
        this_val = vals.get("올해", 0)
        last_val = vals.get("작년", 0)
        if last_val and last_val != 0:
            yoy = round((this_val - last_val) / last_val * 100, 1)
        else:
            yoy = None
        rows.append({
            "키워드":   kw,
            "올해평균": this_val,
            "작년평균": last_val,
            "YoY증감율": yoy,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("YoY증감율", ascending=False, na_position='last').reset_index(drop=True)

    return df

def fetch_gender_age_trend(
    keywords: list,
    days: int = 90,
    time_unit: str = "week",
    progress_callback=None,
) -> dict:
    """
    성별/연령별 키워드 트렌드 수집
    반환: {"gender_df": DataFrame, "age_df": DataFrame}
    """
    url        = "https://openapi.naver.com/v1/datalab/search"
    start_date, end_date = get_date_range(days)
    batches    = [keywords[i:i+5] for i in range(0, len(keywords), 5)]
    total      = len(batches)

    # ── 성별 수집 ──────────────────────────────
    gender_rows = []
    for gender_code, gender_name in [("m", "남성"), ("f", "여성")]:
        for idx, batch in enumerate(batches):
            if progress_callback:
                progress_callback(
                    idx / total,
                    f"성별 트렌드 수집 중... ({gender_name} {idx+1}/{total})"
                )
            keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in batch]
            body = {
                "startDate":     start_date,
                "endDate":       end_date,
                "timeUnit":      time_unit,
                "keywordGroups": keyword_groups,
                "device":        "",
                "gender":        gender_code,
                "ages":          [],
            }
            try:
                r = requests.post(url, json=body, headers=HEADERS, timeout=10)
                r.raise_for_status()
                for result in r.json().get("results", []):
                    kw_name = result["title"]
                    vals    = [item["ratio"] for item in result.get("data", [])]
                    avg     = round(sum(vals) / len(vals), 1) if vals else 0
                    gender_rows.append({"키워드": kw_name, "성별": gender_name, "검색지수": avg})
            except Exception as e:
                print(f"[WARN] 성별 배치 실패 ({gender_name}): {e}")
            time.sleep(1.5)

    # ── 연령별 수집 (5구간으로 묶음) ───────────
    age_groups = [
        (["2"],       "10대"),
        (["3", "4"],  "20대"),
        (["5", "6"],  "30대"),
        (["7"],       "40대"),
        (["8"],       "50대이상"),
    ]
    age_rows = []
    for age_codes, age_name in age_groups:
        for idx, batch in enumerate(batches):
            if progress_callback:
                progress_callback(
                    idx / total,
                    f"연령별 트렌드 수집 중... ({age_name} {idx+1}/{total})"
                )
            keyword_groups = [{"groupName": kw, "keywords": [kw]} for kw in batch]
            body = {
                "startDate":     start_date,
                "endDate":       end_date,
                "timeUnit":      time_unit,
                "keywordGroups": keyword_groups,
                "device":        "",
                "gender":        "",
                "ages":          age_codes,
            }
            try:
                r = requests.post(url, json=body, headers=HEADERS, timeout=10)
                r.raise_for_status()
                for result in r.json().get("results", []):
                    kw_name = result["title"]
                    vals    = [item["ratio"] for item in result.get("data", [])]
                    avg     = round(sum(vals) / len(vals), 1) if vals else 0
                    age_rows.append({"키워드": kw_name, "연령대": age_name, "검색지수": avg})
            except Exception as e:
                print(f"[WARN] 연령 배치 실패 ({age_name}): {e}")
            time.sleep(1.5)

    return {
        "gender_df": pd.DataFrame(gender_rows),
        "age_df":    pd.DataFrame(age_rows),
    }
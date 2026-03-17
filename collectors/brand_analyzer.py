"""
브랜드 분석 모듈
- URL 크롤링 → Gemini 1차 분석 → Gemini 웹검색 2차 분석
- 브랜드 컨텍스트를 AI 인사이트에 주입
"""

import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def crawl_url(url: str) -> str:
    """URL 크롤링 → 텍스트 추출"""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "meta", "link", "header", "footer", "nav"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # 너무 길면 앞 3000자만 사용
        return text[:3000]

    except Exception as e:
        print(f"[WARN] 크롤링 실패: {e}")
        return ""


def analyze_brand(url: str) -> dict:
    """
    브랜드 분석 2단계
    1단계: URL 크롤링 → Gemini 1차 분석
    2단계: Gemini google_search로 브랜드 추가 조사
    반환: {"brand_name": str, "products": str, "context": str}
    """
    result = {
        "brand_name": "",
        "products":   "",
        "context":    "",
    }

    # ── 1단계: URL 크롤링 + Gemini 1차 분석 ──────────────
    print("[INFO] 브랜드 URL 크롤링 중...")
    raw_text = crawl_url(url)

    if not raw_text:
        print("[WARN] 크롤링 실패 — 브랜드 분석 스킵")
        return result

    prompt_1st = f"""아래는 한 브랜드 홈페이지에서 추출한 텍스트입니다.
다음 항목을 간결하게 정리해주세요.

[홈페이지 텍스트]
{raw_text}

[정리 항목]
1. 브랜드명 (공식 브랜드명)
2. 브랜드 소개 (1~2줄 요약)
3. 주요 제품 카테고리 (콤마 구분)
4. 대표 제품명 목록 (확인 가능한 것만, 콤마 구분)
5. 타겟 고객층 (성별, 연령대 추정)

JSON 형식 없이 항목별로 간결하게 답해주세요."""

    try:
        print("[INFO] Gemini 1차 분석 중...")
        r1 = client.models.generate_content(
            model    = "gemini-2.5-flash",
            contents = prompt_1st,
        )
        first_analysis = r1.text
        print(f"[INFO] 1차 분석 완료:\n{first_analysis[:200]}...")
    except Exception as e:
        print(f"[WARN] Gemini 1차 분석 실패: {e}")
        first_analysis = ""

    # 브랜드명 추출 (첫 번째 줄에서)
    brand_name = ""
    for line in first_analysis.split("\n"):
        if "브랜드명" in line or "1." in line:
            brand_name = line.split(":")[-1].strip().replace("**", "")
            if brand_name:
                break

    result["brand_name"] = brand_name or url

    # ── 2단계: Gemini google_search로 브랜드 추가 조사 ───
    print(f"[INFO] Gemini 웹검색으로 '{brand_name}' 추가 조사 중...")

    search_prompt = f"""한국 브랜드 '{brand_name}'에 대해 검색해서 아래 정보를 파악해주세요.

1. 브랜드 포지셔닝 (어떤 컨셉의 브랜드인지)
2. 주요 판매 제품 전체 목록
3. 핵심 성분 또는 원료
4. 주요 타겟 고객 (성별, 연령대)
5. 경쟁 브랜드 대비 차별점
6. 현재 주력 판매 채널 (자사몰, 쿠팡, 네이버 등)

실무 마케터와 MD가 활용할 수 있도록 구체적으로 정리해주세요."""

    try:
        r2 = client.models.generate_content(
            model    = "gemini-2.5-flash",
            contents = search_prompt,
            config   = types.GenerateContentConfig(
                tools = [types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        second_analysis = r2.text
        print(f"[INFO] 2차 웹검색 분석 완료:\n{second_analysis[:200]}...")
    except Exception as e:
        print(f"[WARN] Gemini 웹검색 실패: {e}")
        second_analysis = ""

    # ── 최종 brand_context 합성 ───────────────────────────
    context = f"""
=== 자사 브랜드 분석 결과 ===

[브랜드명]
{brand_name}

[홈페이지 분석]
{first_analysis}

[웹 검색 추가 정보]
{second_analysis}
""".strip()

    result["products"] = first_analysis
    result["context"]  = context

    print("[INFO] 브랜드 분석 완료!")
    return result

def extract_brand_structured(brand_context: str) -> dict:
    """
    브랜드 컨텍스트에서 구조화 데이터 추출
    반환: {
        "target_gender": "남성"/"여성"/"전체",
        "target_ages":   ["30대", "40대"],
        "own_keywords":  ["아르기닌", "마카", ...]
    }
    """
    prompt = f"""아래 브랜드 분석 결과를 읽고, 반드시 아래 JSON 형식으로만 답하세요.
다른 텍스트, 설명, 마크다운 없이 JSON만 출력하세요.

[브랜드 분석 결과]
{brand_context}

[출력 형식]
{{
    "target_gender": "남성" 또는 "여성" 또는 "전체",
    "target_ages": ["10대","20대","30대","40대","50대이상"] 중 해당되는 것만,
    "own_keywords": ["제품명이나 주성분을 개별 키워드로", ...]
}}

own_keywords는 제품명과 핵심 성분을 모두 포함하되, 한 단어씩 분리해서 넣어주세요.
예: ["아르기닌", "마카", "블랙마카", "프로틴", "밀크씨슬", "오메가3"]"""

    try:
        r = client.models.generate_content(
            model    = "gemini-2.5-flash",
            contents = prompt,
        )
        import json, re
        text = r.text.strip()
        # JSON 블록만 추출
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[WARN] 구조화 추출 실패: {e}")

    return {
        "target_gender": "전체",
        "target_ages":   [],
        "own_keywords":  [],
    }
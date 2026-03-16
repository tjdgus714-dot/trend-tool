@echo off
cd /d "C:\Users\opera\OneDrive\바탕 화면\trend-tool"
git add .
git commit -m "update"
git push origin main
pause
```

---

**3단계: `.gitignore` 파일 만들기** (민감 정보 제외)
```
.env
naver.ini
__pycache__/
*.pyc
.streamlit/secrets.toml
```

---

**4단계: `requirements.txt` 확인**
```
streamlit
pandas
plotly
pyyaml
requests
python-dotenv
google-generativeai
pytrends
selenium
webdriver-manager
openpyxl
naver-search-ad
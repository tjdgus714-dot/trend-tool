import requests
import json

COOKIE = '__utma=10102256.948733939.1773638849.1773649430.1773649430.1; __Secure-BUCKET=CN0D; SEARCH_SAMESITE=CgQI_58B; SID=g.a0007ggS1AoBVPwd2a_G3YulInLHkMc6n2xK44jgF7a0p8txpIOhvIOqwxoYNYWq7aemxKEYEQACgYKARUSARUSFQHGX2MiteA5e_X-qdBnYclY6pX_KhoVAUF8yKqhc8PlrreoZKIpcvq0tggV0076; NID=529=cdpX4OPGDO9q_xDSQukOpijBfccpufXy863utH6gaj4KXPtjG1urVNIkClYuDNgvKaNDWbsnebRgmyqUYjLe15umQ9pQv33z9Dib2AVqG8STpYAgoDXnTlhUNZMqEEZzf5VsRCX7utG3vvYjIHwbtrVYyXwxZm48fYQ3v3gBvOeLa8dLeWTlkt6kXFtUoZXuI6riOcFCsnlezyND3ASg; __Secure-1PSID=g.a0007ggS1AoBVPwd2a_G3YulInLHkMc6n2xK44jgF7a0p8txpIOh2Cqw0COLPZxX-0cHnQNLYAACgYKAWISARUSFQHGX2Mi3FQy5_GbsCifCVbsy5EAKBoVAUF8yKogUpUS-ZUpUrxrA88yo4sO0076; __Secure-3PSID=g.a0007ggS1AoBVPwd2a_G3YulInLHkMc6n2xK44jgF7a0p8txpIOhUNDgWOxkkqgAuDE6CscX9QACgYKAX4SARUSFQHGX2MiumIjVglM4aoTYHUM-7EQtxoVAUF8yKo213RLdfVsVY3bbci0P33f0076'

headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'referer': 'https://trends.google.com/trends/explore?q=%EC%9C%A0%EC%82%B0%EA%B7%A0&geo=KR',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'x-browser-channel': 'stable',
    'x-browser-copyright': 'Copyright 2026 Google LLC. All Rights reserved.',
    'x-browser-validation': 'mGtxj/IERUi4uQ9hLSvZZF4DQgA=',
    'x-browser-year': '2026',
    'x-client-data': 'CJK2yQEIprbJAQipncoBCMT8ygEIk6HLAQiFoM0BCNWjzwEIjKzPAQjRsM8BCNe3zwEY7IXPARj1tM8BGK+3zwE=',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'cookie': COOKIE,
}

explore_url = 'https://trends.google.com/trends/api/explore'
explore_params = {
    'hl': 'ko',
    'tz': '-540',
    'req': json.dumps({
        "comparisonItem": [{"keyword": "유산균", "geo": "KR", "time": "today 3-m"}],
        "category": 0,
        "property": ""
    }),
}

r = requests.get(explore_url, params=explore_params, headers=headers, timeout=15)
print(f'explore status: {r.status_code}')
print(r.text[:200])
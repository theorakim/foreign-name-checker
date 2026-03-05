"""
외래어 표기법 검사기 — 웹 UI
Flask 백엔드 + 프론트엔드
"""

import os
import re
import time
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from kiwipiepy import Kiwi

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("KORNORMS_API_KEY")
API_URL = "https://korean.go.kr/kornorms/exampleReqList.do"

kiwi = Kiwi()

# 흔한 한국어 단어 (고유명사 후보에서 제외)
_COMMON_KOREAN = {
    "우리", "자신", "여성", "남성", "사람", "누구", "모두", "하나",
    "작품", "예술", "공간", "사진", "제목", "소재", "감각", "개념",
    "대상", "경험", "형태", "방식", "지식", "균형", "의미", "관계",
    "해방", "행위", "요소", "초점", "기반", "경계", "범주", "재료",
    "연상", "생각", "접촉", "표면", "정서", "감각", "촉각", "시각",
    "미학", "섬유", "장식", "변형", "일상", "전시", "운동", "황동",
    "관객", "소재", "부담", "온도", "혼란", "감탄", "지면", "지위",
    "열쇠", "온몸", "쾌감", "고통", "직조", "보풀", "주렴", "감상",
    "체화", "함의", "이해", "조율", "형식", "정수", "사실", "수용",
    "고유", "운동", "제안", "후자", "안다", "로저", "아르",
    # 외래어 패턴에 걸리지만 한국어인 단어
    "포함", "토대", "토론", "투자", "태도", "파악", "파괴", "판단",
    "폭력", "피해", "학교", "학생", "탄생", "태양", "특히", "통해",
    "코너", "코드", "아티스트", "가능", "가족", "감독", "감정",
    "결과", "결국", "관점", "교육", "구조", "기술", "기억", "기준",
    "기타", "노력", "도구", "도시", "독자", "동시", "목적", "문제",
    "문화", "물질", "미래", "방법", "본질", "부분", "분야", "불가",
    "비롯", "사건", "사실", "사회", "상태", "색채", "성격", "세계",
    "소설", "속도", "수준", "시대", "시작", "실제", "영향", "예측",
    "완성", "위치", "이후", "인간", "인물", "자체", "장소", "전체",
    "정보", "정치", "조건", "존재", "주요", "중요", "증가", "지역",
    "차이", "최초", "추구", "표현", "필요", "현대", "현실", "확인",
    "환경", "활동", "효과",
}


def _has_foreign_pattern(word):
    """외래어에서 흔한 패턴이 있는지 체크"""
    foreign_end = set('크트프스즈드그브흐')
    aspirated = set('카타파키티피쿠투푸코토포케테페캐태패')
    # 외래어에서 흔한 음절들
    foreign_syllables = set('핸폰브젝션웨워랜렌런벨젤맨톤넷벳펀')
    if word[-1] in foreign_end:
        return True
    if any(ch in aspirated for ch in word):
        return True
    if '르' in word or '슈' in word or '츠' in word or '오브' in word:
        return True
    # 외래어 음절이 2개 이상이면 외래어로 판단
    if sum(1 for ch in word if ch in foreign_syllables) >= 2:
        return True
    return False


def _trim_prefix(name):
    """괄호 패턴에서 잡힌 이름 앞의 일반어를 제거한다."""
    prefix_words = {
        "아티스트", "작가", "감독", "배우", "교수", "박사", "선수",
        "대통령", "총리", "장관", "화가", "작곡가", "철학자", "소설가",
        "시인", "건축가", "디자이너", "프로듀서", "기자",
    }
    parts = name.split()
    while len(parts) > 1 and parts[0] in prefix_words:
        parts.pop(0)
    return " ".join(parts)


def extract_candidates(text):
    """텍스트에서 외래어 후보를 추출한다."""
    candidates = set()

    # 괄호 패턴 — "레오노르 안투네스(Leonor Antunes)" 형태
    paren_pattern = re.compile(r'([가-힣]+(?:\s[가-힣]+){0,3})\s*\(([A-Za-z][\w\s\.\-\']+)\)')
    for match in paren_pattern.finditer(text):
        korean_name = _trim_prefix(match.group(1).strip())
        if len(korean_name.replace(" ", "")) >= 2:
            candidates.add(korean_name)

    # kiwipiepy 형태소 분석
    result = kiwi.analyze(text)
    tokens = result[0][0]

    # NNP(고유명사) 태그 + 연속 병합
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.tag == "NNP":
            merged_end = token.start + token.len
            parts = [token.form]
            j = i + 1
            while j < len(tokens):
                next_t = tokens[j]
                gap = next_t.start - merged_end
                if next_t.tag == "NNP" and 0 <= gap <= 1:
                    if gap == 1:
                        parts.append(" ")
                    parts.append(next_t.form)
                    merged_end = next_t.start + next_t.len
                    j += 1
                else:
                    break
            merged = "".join(parts)
            i = j
            clean = merged.replace(" ", "")
            if len(clean) >= 2 and all('가' <= ch <= '힣' for ch in clean):
                candidates.add(merged)
        else:
            i += 1

    # NNG(일반명사) 중 외래어 패턴이 있는 것도 후보로 추가
    for token in tokens:
        if token.tag == "NNG" and len(token.form) >= 2:
            if all('가' <= ch <= '힣' for ch in token.form):
                if _has_foreign_pattern(token.form) and token.form not in _COMMON_KOREAN:
                    candidates.add(token.form)

    # 조사 제거 + 외래어 패턴
    josa_pattern = re.compile(
        r'(은|는|이|가|을|를|에|의|도|로|으로|와|과|에서|에게|부터|까지|처럼|라는|이란|에는|에서는)$'
    )
    for raw_word in re.findall(r'[가-힣]{3,}', text):
        stripped = josa_pattern.sub('', raw_word)
        if len(stripped) >= 3 and stripped != raw_word and _has_foreign_pattern(stripped):
            candidates.add(stripped)

    # 필터링
    filtered = []
    for c in sorted(candidates):
        clean = c.replace(" ", "")
        if len(clean) <= 1:
            continue
        if clean in _COMMON_KOREAN:
            continue
        filtered.append(c)

    # 중복 제거: 짧은 후보가 긴 후보에 포함되면 긴 쪽 제거
    deduped = []
    for i, a in enumerate(filtered):
        a_clean = a.replace(" ", "")
        is_superset = False
        for j, b in enumerate(filtered):
            if i == j:
                continue
            b_clean = b.replace(" ", "")
            # a가 b를 포함하고 a가 더 길면 → a는 중복 (b만 남김)
            if b_clean in a_clean and len(a_clean) > len(b_clean):
                is_superset = True
                break
        if not is_superset:
            deduped.append(a)

    return deduped


def search_kornorms(keyword, search_type="equal"):
    """국립국어원 API 검색"""
    if not API_KEY:
        return None
    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 10,
        "langType": "0003",
        "resultType": "json",
        "searchEquals": search_type,
        "searchKeyword": keyword,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def parse_items(data):
    """API 응답에서 items 추출"""
    if not data:
        return []
    try:
        return data.get("response", {}).get("items") or []
    except (AttributeError, TypeError):
        return []


def is_similar(w1, w2):
    """유사도 판별"""
    if w1 in w2 or w2 in w1:
        return True
    if len(w1) >= 2 and len(w2) >= 2 and w1[:2] == w2[:2]:
        return True
    if abs(len(w1) - len(w2)) <= 2:
        common = sum(1 for ch in w1 if ch in w2)
        if common / max(len(w1), len(w2)) >= 0.5:
            return True
    return False


def is_chinese(item):
    """중국어/일본어 한자 음역 판별"""
    src = item.get("srclang_mark", "")
    lang = item.get("lang_nm", "") or ""
    guk = item.get("guk_nm", "") or ""
    if "중국어" in lang or "일본어" in lang:
        return True
    if "중국" in guk or "일본" in guk:
        return True
    if re.search(r'[\u4e00-\u9fff]', src):
        return True
    return False


def check_word(word):
    """단어 하나를 검사해서 결과를 반환한다."""
    clean = word.replace(" ", "")

    # 1차: 정확히 일치
    data = search_kornorms(clean, "equal")
    items = parse_items(data)

    if items:
        for item in items:
            korean = item.get("korean_mark", "").strip()
            if korean == clean and not is_chinese(item):
                return {
                    "word": word,
                    "status": "correct",
                    "korean": korean,
                    "original": item.get("srclang_mark", ""),
                    "country": item.get("guk_nm", ""),
                    "language": item.get("lang_nm", ""),
                    "category": item.get("foreign_gubun", ""),
                }

    time.sleep(0.15)

    # 2차: 부분 일치
    data = search_kornorms(clean, "like")
    items = parse_items(data)

    if items:
        relevant = []
        for item in items:
            korean = item.get("korean_mark", "").strip()
            if korean and is_similar(clean, korean) and not is_chinese(item):
                relevant.append({
                    "korean": korean,
                    "original": item.get("srclang_mark", ""),
                    "country": item.get("guk_nm", ""),
                    "language": item.get("lang_nm", ""),
                    "category": item.get("foreign_gubun", ""),
                })

        if relevant:
            return {
                "word": word,
                "status": "check",
                "suggestions": relevant[:3],
            }

    return {"word": word, "status": "not_found"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """텍스트에서 고유명사 후보를 추출"""
    text = request.json.get("text", "")
    if not text.strip():
        return jsonify({"candidates": []})
    candidates = extract_candidates(text)
    return jsonify({"candidates": candidates})


@app.route("/api/check", methods=["POST"])
def api_check():
    """선택된 단어들을 검사"""
    words = request.json.get("words", [])
    results = []
    checked = set()
    for word in words:
        clean = word.replace(" ", "")
        if clean in checked:
            continue
        checked.add(clean)
        result = check_word(word)
        results.append(result)
        time.sleep(0.15)
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(debug=True, port=5001)

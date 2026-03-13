"""
외래어 표기법 검사기 — 웹 UI
Flask 백엔드 + 프론트엔드
"""

import os
import re
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from kiwipiepy import Kiwi

logging.basicConfig(level=logging.INFO)

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
    "아우르", "패턴", "미학적",
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
    foreign_syllables = set('핸폰브젝션웨워랜렌런벨젤맨톤넷벳펀')
    if word[-1] in foreign_end:
        return True
    if any(ch in aspirated for ch in word):
        return True
    if '르' in word or '슈' in word or '츠' in word or '오브' in word:
        return True
    if sum(1 for ch in word if ch in foreign_syllables) >= 2:
        return True
    return False


def _has_strong_foreign_pattern(word):
    """외래어일 가능성이 높은 강한 패턴 체크 (비엔날레, 아르세날레 등)"""
    strong_patterns = [
        '날레', '나레', '셋날', '엔날', '스터', '슈타', '르투',
        '비엔', '갈레', '르셋', '르세',
    ]
    if any(p in word for p in strong_patterns):
        return True
    foreign_end = set('크트프스즈드그브흐')
    aspirated = set('카타파키티피쿠투푸코토포케테페캐태패')
    score = 0
    if word[-1] in foreign_end:
        score += 2
    score += sum(1 for ch in word if ch in aspirated)
    if '르' in word or '슈' in word or '츠' in word:
        score += 1
    return score >= 3


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


def _is_likely_korean_phrase(text):
    """NNP 체인이 실제로는 한국어 일반 문구인지 판별한다."""
    words = text.split()
    if len(words) <= 2:
        return False
    common_count = sum(1 for w in words if w in _COMMON_KOREAN or len(w) == 1)
    return common_count >= len(words) // 2


def extract_candidates(text):
    """텍스트에서 외래어 후보를 추출한다."""
    candidates = set()

    # 괄호 패턴 — "레오노르 안투네스(Leonor Antunes)" 형태
    paren_pattern = re.compile(r'([가-힣]+(?:\s[가-힣]+){0,3})\s*\(([A-Za-z][\w\s\.\-\']+)\)')
    for match in paren_pattern.finditer(text):
        korean_name = _trim_prefix(match.group(1).strip())
        # 일반 한국어 구절이 딸려온 경우 필터링
        words = korean_name.split()
        # 뒤에서부터 외래어 패턴이 있는 단어만 취한다
        foreign_words = []
        for w in reversed(words):
            if w in _COMMON_KOREAN or (not _has_foreign_pattern(w) and len(w) <= 2):
                break
            foreign_words.insert(0, w)
        if foreign_words:
            for w in foreign_words:
                if len(w) >= 2:
                    candidates.add(w)
        else:
            continue  # 외래어 부분이 없으면 스킵

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
            if " " in merged:
                for part in merged.split():
                    if len(part) >= 2 and all('가' <= ch <= '힣' for ch in part):
                        if not _is_likely_korean_phrase(part):
                            candidates.add(part)
            else:
                clean = merged.replace(" ", "")
                if len(clean) >= 2 and all('가' <= ch <= '힣' for ch in clean):
                    if not _is_likely_korean_phrase(merged):
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

    # 원문에서 직접 외래어 패턴 단어 추출 (형태소 분석기가 잘못 쪼갠 경우 대비)
    # 공백으로 나뉜 어절 단위로 체크
    for raw_word in re.findall(r'[가-힣]{3,}', text):
        stripped = josa_pattern.sub('', raw_word)
        if len(stripped) >= 3 and stripped not in _COMMON_KOREAN:
            # 외래어 특유 패턴이 강하게 나타나는 경우
            if _has_strong_foreign_pattern(stripped):
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

    # 중복 제거: 서브셋 관계인 후보 쌍에서 하나만 남김
    # 긴 후보가 모두 외래어로 보이면 긴 쪽을 남기고 (이름 전체 보존)
    # 긴 후보에 일반 한국어가 섞여있으면 짧은 쪽을 남김
    to_remove = set()
    for i, a in enumerate(filtered):
        a_clean = a.replace(" ", "")
        for j, b in enumerate(filtered):
            if i == j or i in to_remove or j in to_remove:
                continue
            b_clean = b.replace(" ", "")
            if b_clean in a_clean and len(a_clean) > len(b_clean):
                # a가 b를 포함하고 a가 더 긴 경우
                a_has_korean = any(w in _COMMON_KOREAN for w in a.split())
                if a_has_korean:
                    to_remove.add(i)  # 긴 쪽에 한국어 섞임 → 긴 쪽 제거
                else:
                    to_remove.add(j)  # 긴 쪽이 전부 외래어 → 짧은 쪽 제거

    deduped = [f for i, f in enumerate(filtered) if i not in to_remove]
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


# 외래어 오타에서 자주 혼동되는 글자 쌍
_CONFUSABLE_PAIRS = [
    ('샵', '숍'), ('숍', '샵'),
    ('칼', '갈'), ('갈', '칼'),
    ('셋', '세'), ('세', '셋'),
    ('쉬', '슈'), ('슈', '쉬'),
    ('씨', '시'), ('시', '씨'),
    ('빠', '파'), ('파', '빠'),
    ('까', '카'), ('카', '까'),
    ('따', '타'), ('타', '따'),
    ('뻬', '페'), ('페', '뻬'),
    ('쩨', '체'), ('체', '쩨'),
    ('렌', '런'), ('런', '렌'),
    ('벨', '밸'), ('밸', '벨'),
    ('보', '보'), ('워', '위'), ('위', '워'),
    ('왜', '웨'), ('웨', '왜'),
    ('애', '에'), ('에', '애'),
    ('오', '어'), ('어', '오'),
]


def _generate_variants(word):
    """흔한 외래어 오타 패턴으로 변형본을 생성한다. 최대 5개."""
    variants = set()
    for old, new in _CONFUSABLE_PAIRS:
        if old in word:
            variants.add(word.replace(old, new, 1))
    # 길이 가까운 것 우선 (원본과 거리가 가까울수록 좋음)
    return sorted(variants, key=lambda v: levenshtein(word, v))[:5]


def levenshtein(s1, s2):
    """두 문자열의 편집 거리를 계산한다. (표준 DP 구현)"""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 삽입, 삭제, 치환 중 최소 비용
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def find_typo_candidates(word, custom_dict, max_distance=2):
    """자체 사전에서 오타 후보를 찾는다."""
    candidates = []
    for dict_key, dict_val in custom_dict.items():
        dist = levenshtein(word, dict_key)
        if 0 < dist <= max_distance:
            candidates.append({
                "word": dict_val if dict_val != dict_key else dict_key,
                "distance": dist,
                "source": "자체 사전"
            })
    # 거리순 정렬, 최대 3개
    return sorted(candidates, key=lambda x: x["distance"])[:3]


def is_similar(w1, w2):
    """유사도 판별 — like 검색 결과 필터용"""
    if w1 == w2:
        return True
    if w1 in w2 or w2 in w1:
        return True
    # 편집 거리 1~2면 유사
    dist = levenshtein(w1, w2)
    if dist <= 2:
        return True
    # 앞 2글자 일치
    if len(w1) >= 2 and len(w2) >= 2 and w1[:2] == w2[:2]:
        return True
    # 길이 비슷하고 글자 절반 이상 겹침
    if abs(len(w1) - len(w2)) <= 2:
        common = sum(1 for ch in w1 if ch in w2)
        if common / max(len(w1), len(w2)) >= 0.4:
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


def check_word(word, custom_dict=None):
    """단어 하나를 검사해서 결과를 반환한다."""
    clean = word.replace(" ", "")

    # 자체 사전 검사 (custom_dict가 있을 때만)
    if custom_dict:
        # 정확 일치: 키에 해당하면 바로 반환
        if clean in custom_dict:
            val = custom_dict[clean]
            if val == clean:
                # 올바른 표기 확인
                return {"word": word, "status": "custom_correct", "source": "자체 사전"}
            else:
                # 교정 필요
                return {"word": word, "status": "custom_fix", "correction": val, "source": "자체 사전"}

        # 오타 매칭: 편집 거리 1~2인 후보 탐색
        typo_hits = find_typo_candidates(clean, custom_dict)
        if typo_hits:
            return {"word": word, "status": "typo_candidate", "similar": typo_hits}

    # 국립국어원 API 검색 — 1차: 정확히 일치
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

    # 2차: 부분 일치 (like 검색)
    data = search_kornorms(clean, "like")
    items = parse_items(data)

    if items:
        relevant = []
        for item in items:
            korean = item.get("korean_mark", "").strip()
            if not korean or is_chinese(item):
                continue
            # like 결과 중 정확 일치가 있으면 correct 처리
            if korean == clean:
                return {
                    "word": word,
                    "status": "correct",
                    "korean": korean,
                    "original": item.get("srclang_mark", ""),
                    "country": item.get("guk_nm", ""),
                    "language": item.get("lang_nm", ""),
                    "category": item.get("foreign_gubun", ""),
                }
            if is_similar(clean, korean):
                dist = levenshtein(clean, korean)
                relevant.append({
                    "korean": korean,
                    "original": item.get("srclang_mark", ""),
                    "country": item.get("guk_nm", ""),
                    "language": item.get("lang_nm", ""),
                    "category": item.get("foreign_gubun", ""),
                    "distance": dist,
                })

        if relevant:
            # 편집 거리순 정렬
            relevant.sort(key=lambda x: x.get("distance", 99))
            return {
                "word": word,
                "status": "check",
                "suggestions": relevant[:3],
            }

    # 3차: 흔한 외래어 오타 패턴으로 변형본을 만들어서 재검색
    # "커피샵"→"커피숍", "포르투칼"→"포르투갈" 등
    variants = _generate_variants(clean)
    for idx, variant in enumerate(variants):
        if idx >= 3:
            break  # API 호출 제한
        time.sleep(0.15)
        data = search_kornorms(variant, "equal")
        items = parse_items(data)
        if items:
            for item in items:
                korean = item.get("korean_mark", "").strip()
                guk = item.get("guk_nm", "") or ""
                # korean_mark 일치 (일반 단어)
                if korean == variant and not is_chinese(item):
                    return {
                        "word": word,
                        "status": "check",
                        "suggestions": [{
                            "korean": korean,
                            "original": item.get("srclang_mark", ""),
                            "country": guk,
                            "language": item.get("lang_nm", ""),
                            "category": item.get("foreign_gubun", ""),
                            "distance": levenshtein(clean, korean),
                        }],
                    }
                # guk_nm 일치 (국가/지역명이 변형본과 같으면 국가명 오타)
                if guk == variant:
                    return {
                        "word": word,
                        "status": "check",
                        "suggestions": [{
                            "korean": variant,
                            "original": guk,
                            "country": "",
                            "language": "",
                            "category": "국가/지역명",
                            "distance": levenshtein(clean, variant),
                        }],
                    }

    # API 키가 없으면 구분해서 알려줌
    if not API_KEY:
        return {"word": word, "status": "no_api_key"}

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
    """선택된 단어들을 병렬로 검사"""
    try:
        words = request.json.get("words", [])
        custom_dict = request.json.get("custom_dict", {}) or None

        # 중복 제거 (순서 유지)
        seen = set()
        unique_words = []
        for w in words:
            clean = w.replace(" ", "")
            if clean not in seen:
                seen.add(clean)
                unique_words.append(w)

        results_map = {}
        # 최대 5개 스레드로 병렬 검사
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_word = {
                executor.submit(check_word, w, custom_dict): w
                for w in unique_words
            }
            for future in as_completed(future_to_word):
                word = future_to_word[future]
                try:
                    results_map[word] = future.result()
                except Exception as e:
                    logging.error(f"check_word 오류 ({word}): {e}")
                    results_map[word] = {"word": word, "status": "error"}

        # 원래 순서로 정렬해서 반환
        results = [results_map[w] for w in unique_words]
        return jsonify({"results": results})

    except Exception as e:
        logging.error(f"api_check 오류: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="0.0.0.0", port=port)

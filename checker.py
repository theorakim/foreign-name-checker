"""
외래어 표기법 검사기
텍스트에서 고유명사 후보를 추출하고, 사용자가 확인/추가한 뒤,
국립국어원 어문 규범 용례 API로 표기법을 확인한다.

흐름: 텍스트 입력 → 고유명사 후보 자동 추출 → 사용자 확인/추가 → API 검색 → 결과 출력
"""

import os
import re
import sys
import time
import requests
from dotenv import load_dotenv
from kiwipiepy import Kiwi

load_dotenv()

API_KEY = os.getenv("KORNORMS_API_KEY")
API_URL = "https://korean.go.kr/kornorms/exampleReqList.do"

kiwi = Kiwi()


def extract_proper_noun_candidates(text):
    """텍스트에서 외래어 고유명사 후보를 추출한다.

    NNP(고유명사) 태그 + 괄호 패턴으로 좁혀서 추출.
    """
    candidates = set()

    # 전략 1: 괄호 패턴 — "레오노르 안투네스(Leonor Antunes)" 형태
    paren_pattern = re.compile(r'([가-힣]+(?:\s[가-힣]+){0,3})\s*\(([A-Za-z][\w\s\.\-\']+)\)')
    for match in paren_pattern.finditer(text):
        korean_name = match.group(1).strip()
        if len(korean_name.replace(" ", "")) >= 2:
            candidates.add(korean_name)

    # 전략 2: kiwipiepy NNP 태그 + 연속 NNP 병합
    result = kiwi.analyze(text)
    tokens = result[0][0]

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

    # 전략 3: 원문에서 조사 제거한 어절 중 외래어 패턴
    josa_pattern = re.compile(
        r'(은|는|이|가|을|를|에|의|도|로|으로|와|과|에서|에게|부터|까지|처럼|라는|이란|에는|에서는)$'
    )
    for raw_word in re.findall(r'[가-힣]{3,}', text):
        stripped = josa_pattern.sub('', raw_word)
        if len(stripped) >= 3 and stripped != raw_word:
            # 외래어 패턴 체크 (격음/경음 포함, 외래어 받침 등)
            if _has_foreign_pattern(stripped):
                candidates.add(stripped)

    # 1글자 제거, 흔한 한국어 단어 제거
    filtered = set()
    for c in candidates:
        clean = c.replace(" ", "")
        if len(clean) <= 1:
            continue
        if clean in _COMMON_KOREAN:
            continue
        filtered.add(c)

    return sorted(filtered)


def _has_foreign_pattern(word):
    """외래어에서 흔한 패턴이 있는지 체크한다."""
    foreign_end = set('크트프스즈드그브흐')
    aspirated = set('카타파키티피쿠투푸코토포케테페캐태패')

    if word[-1] in foreign_end:
        return True
    if any(ch in aspirated for ch in word):
        return True
    if '르' in word or '슈' in word or '츠' in word:
        return True
    return False


# 흔한 한국어 단어 (고유명사 후보에서 제외)
_COMMON_KOREAN = {
    "우리", "자신", "여성", "남성", "사람", "누구", "모두", "하나",
    "작품", "예술", "공간", "사진", "제목", "소재", "감각", "개념",
    "대상", "경험", "형태", "방식", "지식", "균형", "의미", "관계",
    "해방", "행위", "요소", "초점", "기반", "경계", "범주", "재료",
    "연상", "생각", "접촉", "표면", "정서", "감각", "촉각", "시각",
    "미학", "섬유", "장식", "변형", "일상", "전시", "운동",
}


def user_select_candidates(candidates):
    """사용자에게 후보 목록을 보여주고 선택/추가를 받는다."""

    print(f"  자동 추출된 후보 {len(candidates)}개:")
    print()

    selected = set(range(len(candidates)))  # 기본적으로 전부 선택

    for i, word in enumerate(candidates):
        print(f"  [{i+1}] {word}")

    print()
    print("  사용법:")
    print("    Enter      → 전부 선택하고 검사 시작")
    print("    1,3,5      → 1, 3, 5번만 선택")
    print("    -2,-4      → 2, 4번 제외")
    print("    +드리스콜  → '드리스콜' 직접 추가")
    print("    여러 줄 입력 가능. 'go' 입력하면 검사 시작")
    print()

    added = []

    while True:
        try:
            line = input("  >> ").strip()
        except EOFError:
            break

        if line == "" or line.lower() == "go":
            break

        # 직접 추가: +단어
        if line.startswith("+"):
            new_word = line[1:].strip()
            if new_word:
                added.append(new_word)
                print(f"    → '{new_word}' 추가됨")
            continue

        # 제외: -번호
        if line.startswith("-"):
            parts = line.split(",")
            for p in parts:
                p = p.strip().lstrip("-")
                try:
                    idx = int(p) - 1
                    if 0 <= idx < len(candidates):
                        selected.discard(idx)
                        print(f"    → '{candidates[idx]}' 제외됨")
                except ValueError:
                    pass
            continue

        # 선택: 번호들
        try:
            nums = [int(x.strip()) for x in line.split(",")]
            selected = set()
            for n in nums:
                if 1 <= n <= len(candidates):
                    selected.add(n - 1)
            print(f"    → {len(selected)}개 선택됨")
        except ValueError:
            # 숫자가 아니면 직접 추가로 처리
            added.append(line)
            print(f"    → '{line}' 추가됨")

    # 최종 목록 만들기
    final = [candidates[i] for i in sorted(selected)]
    final.extend(added)

    return final


def _is_similar(search_word, result_word):
    """검색어와 API 결과가 관련 있는지 판별한다."""
    if search_word in result_word or result_word in search_word:
        return True

    min_len = min(len(search_word), len(result_word))
    if min_len >= 2 and search_word[:2] == result_word[:2]:
        return True

    if abs(len(search_word) - len(result_word)) <= 2:
        common = sum(1 for ch in search_word if ch in result_word)
        ratio = common / max(len(search_word), len(result_word))
        if ratio >= 0.5:
            return True

    return False


def _is_chinese_match(item):
    """API 결과가 중국어/일본어 한자 음역인지 판별한다."""
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


def search_kornorms(keyword, search_type="equal"):
    """국립국어원 어문 규범 용례 API에서 검색한다."""
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


def parse_api_response(data):
    """API 응답에서 items를 추출한다."""
    if not data:
        return []
    try:
        response = data.get("response", {})
        return response.get("items") or []
    except (AttributeError, TypeError):
        return []


def check_words(words):
    """선택된 단어들을 API로 검사한다."""

    print()
    print(f"[검사 중] {len(words)}개 단어 조회...")

    found = {}
    suggestions = {}
    searched = {}

    for idx, word in enumerate(words):
        clean = word.replace(" ", "")

        if clean in searched:
            continue

        time.sleep(0.15)
        searched[clean] = True

        # 1차: 정확히 일치
        data = search_kornorms(clean, "equal")
        items = parse_api_response(data)

        exact = None
        if items:
            for item in items:
                korean = item.get("korean_mark", "").strip()
                if korean == clean:
                    exact = item
                    break

        if exact:
            found[word] = exact
        else:
            # 2차: 부분 일치
            time.sleep(0.15)
            data = search_kornorms(clean, "like")
            items = parse_api_response(data)

            if items:
                relevant = []
                for item in items:
                    korean = item.get("korean_mark", "").strip()
                    if korean and _is_similar(clean, korean):
                        relevant.append(item)
                if relevant:
                    suggestions[word] = relevant

    # 결과 출력
    print()
    print("[결과]")
    print("-" * 60)

    if not found and not suggestions:
        print("  용례를 찾지 못했어.")
        # 검색했지만 결과 없는 단어들 표시
        no_result = [w for w in words if w.replace(" ", "") in searched
                     and w not in found and w not in suggestions]
        if no_result:
            print()
            print("  API에 등록되지 않은 단어:")
            for w in no_result:
                print(f"    ? {w}")
        print("-" * 60)
        return

    correct_count = 0
    check_count = 0

    for word, item in sorted(found.items()):
        if _is_chinese_match(item):
            continue
        correct_count += 1
        src = item.get("srclang_mark", "")
        lang = item.get("lang_nm", "")
        guk = item.get("guk_nm", "")
        gubun = item.get("foreign_gubun", "")
        print(f"  ✓ {word} — 올바른 표기 (원어: {src}, {guk}/{lang}, {gubun})")

    for word, items in sorted(suggestions.items()):
        word_clean = word.replace(" ", "")
        if any(word_clean in f.replace(" ", "") or f.replace(" ", "") in word_clean for f in found):
            continue

        relevant_items = [it for it in items if not _is_chinese_match(it)]
        if not relevant_items:
            continue

        check_count += 1
        print(f"  ✗ {word} — 확인 필요!")
        for item in relevant_items[:3]:
            korean = item.get("korean_mark", "")
            src = item.get("srclang_mark", "")
            lang = item.get("lang_nm", "")
            guk = item.get("guk_nm", "")
            gubun = item.get("foreign_gubun", "")
            print(f"    → 권장 표기: {korean} (원어: {src}, {guk}/{lang}, {gubun})")

    # 검색했지만 결과 없는 단어
    no_result = [w for w in words if w.replace(" ", "") in searched
                 and w not in found and w not in suggestions]
    if no_result:
        print()
        for w in no_result:
            print(f"  ? {w} — 용례 없음")

    print("-" * 60)
    print(f"  ✓ 올바름 {correct_count} | ✗ 확인필요 {check_count} | ? 용례없음 {len(no_result)}")
    print()


def main():
    """메인 실행 함수."""

    # 텍스트 입력
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"파일을 찾을 수 없어: {filepath}")
            sys.exit(1)
    else:
        print("검사할 텍스트를 입력해 (빈 줄 두 번으로 입력 완료):")
        print()
        lines = []
        empty_count = 0
        while True:
            try:
                line = input()
                if line == "":
                    empty_count += 1
                    if empty_count >= 2:
                        break
                    lines.append(line)
                else:
                    empty_count = 0
                    lines.append(line)
            except EOFError:
                break
        text = "\n".join(lines)

    if not text.strip():
        print("텍스트가 비어있어.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  외래어 표기법 검사기")
    print("=" * 60)
    print()

    # 1단계: 고유명사 후보 추출
    print("[1단계] 고유명사 후보 추출")
    candidates = extract_proper_noun_candidates(text)

    if not candidates:
        print("  → 고유명사 후보를 찾지 못했어.")
        print("  직접 입력해줘 (한 줄에 하나씩, 빈 줄로 완료):")
        added = []
        while True:
            try:
                line = input("  >> ").strip()
                if not line:
                    break
                added.append(line)
            except EOFError:
                break
        if not added:
            print("  검사할 단어가 없어.")
            return
        check_words(added)
        return

    # 2단계: 사용자 확인
    print()
    print("[2단계] 검사할 단어 선택")
    selected = user_select_candidates(candidates)

    if not selected:
        print("  검사할 단어가 없어.")
        return

    print(f"  → 최종 {len(selected)}개: {', '.join(selected)}")

    # 3단계: API 검색
    check_words(selected)


if __name__ == "__main__":
    main()

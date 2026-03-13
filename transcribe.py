"""
외래어 표기법 규칙 기반 변환기
국립국어원 외래어 표기법(문화체육관광부 고시) 제3장 표기 세칙 기반
"""

import re

# ── 한글 음절 조합 유틸 ──────────────────────────────────────────

# 초성(19개) 인덱스
_ONSET_IDX = {
    'ㄱ': 0, 'ㄲ': 1, 'ㄴ': 2, 'ㄷ': 3, '㄄': 4, 'ㄹ': 5,
    'ㅁ': 6, 'ㅂ': 7, 'ㅃ': 8, 'ㅅ': 9, 'ㅆ': 10, 'ㅇ': 11,
    'ㅈ': 12, 'ㅉ': 13, 'ㅊ': 14, 'ㅋ': 15, 'ㅌ': 16, 'ㅍ': 17, 'ㅎ': 18,
}

def _is_hangul(ch):
    return 0xAC00 <= ord(ch) <= 0xD7A3

def _onset_of(ch):
    """한글 음절의 초성 인덱스를 반환 (ㅇ=11이면 모음으로 시작)"""
    if not _is_hangul(ch):
        return -1
    return (ord(ch) - 0xAC00) // (21 * 28)

def _replace_onset(ch, new_onset_idx):
    """한글 음절의 초성을 교체"""
    idx = ord(ch) - 0xAC00
    rest = idx % (21 * 28)
    return chr(0xAC00 + new_onset_idx * 21 * 28 + rest)

def _jamo_to_syllable(jamo, vowel_idx=18):
    """자음 자모 + 모음 인덱스(기본 ㅡ=18) → 음절"""
    o = _ONSET_IDX.get(jamo, 11)
    return chr(0xAC00 + o * 21 * 28 + vowel_idx * 28)

def _assemble(segments):
    """
    세그먼트 목록을 한국어 문자열로 조합.
    세그먼트는 완성형 한글 문자열 또는 단독 자음 자모(ㄱ,ㄴ,...).
    단독 자음이 모음으로 시작하는 다음 세그먼트 앞에 있으면 초성으로 결합.
    """
    out = []
    i = 0
    while i < len(segments):
        seg = segments[i]

        # 단독 자음 자모 1개
        if len(seg) == 1 and seg in _ONSET_IDX:
            onset_idx = _ONSET_IDX[seg]
            # 다음 세그먼트가 모음 시작 음절이면 결합
            if i + 1 < len(segments):
                nxt = segments[i + 1]
                if nxt and _is_hangul(nxt[0]) and _onset_of(nxt[0]) == 11:
                    out.append(_replace_onset(nxt[0], onset_idx) + nxt[1:])
                    i += 2
                    continue
            # 결합 불가 → ㅡ 모음 붙여서 독립 음절
            out.append(_jamo_to_syllable(seg))
            i += 1
            continue

        # 복합 자모 (예: 'ㄱㅅ' → 두 음절)
        if len(seg) == 2 and all(c in _ONSET_IDX for c in seg):
            for j, jamo in enumerate(seg):
                onset_idx = _ONSET_IDX[jamo]
                # 첫 자모이고 다음 세그먼트가 모음 시작이면 결합
                if j == 0 and i + 1 < len(segments):
                    nxt = segments[i + 1]
                    if nxt and _is_hangul(nxt[0]) and _onset_of(nxt[0]) == 11:
                        out.append(_replace_onset(nxt[0], onset_idx) + nxt[1:])
                        # 나머지 자모는 독립 처리 필요 없이 skip (두 번째 자모는 별도 음절)
                        continue
                out.append(_jamo_to_syllable(jamo))
            i += 1
            continue

        out.append(seg)
        i += 1

    return ''.join(out)


# ── 언어 감지 ────────────────────────────────────────────────────

def detect_language(text):
    """특수 문자 기반 언어 감지. 확인 불가능하면 None 반환."""
    t = text.lower()
    if any(c in t for c in 'äöüß'):
        return 'de'
    if 'ñ' in t:
        return 'es'
    if any(c in t for c in 'ãõ'):
        return 'pt'
    if any(c in t for c in 'éèêëàâîïôûùüçœæ'):
        return 'fr'
    return 'en'  # 특수 문자 없으면 영어로 간주


# ── 영어 표기법 ─────────────────────────────────────────────────

def _transcribe_english(word):
    """
    영어 단어 → 한국어 표기 + 적용 규칙 목록
    국립국어원 외래어 표기법 제3장 제1절 영어 규정 적용
    """
    w = re.sub(r"[^a-zA-Z]", '', word).lower()
    if not w:
        return word, []

    n = len(w)
    segments = []
    rules = []

    def ch(offset=0):
        idx = i + offset
        return w[idx] if 0 <= idx < n else ''

    def is_v(c):
        return c in 'aeiou'

    def nv(offset=1):
        return is_v(ch(offset))

    def add(seg, rule):
        segments.append(seg)
        if rule and rule not in rules:
            rules.append(rule)

    i = 0
    while i < n:
        c = ch()
        rest = w[i:]

        # ── 3자 패턴 ──
        if rest.startswith('tch'):
            add('치', 'tch → 치 [제1절 1항]'); i += 3; continue
        if rest.startswith('sch'):
            add('슈', 'sch → 슈 [제1절 1항]'); i += 3; continue

        # ── 2자 패턴 ──
        if rest.startswith('ck'):
            add('ㅋ' if nv(2) else '크',
                'ck → ㅋ (모음 앞) / 크 (자음 앞·어말) [제1절 1항]')
            i += 2; continue

        if rest.startswith('ch'):
            add('ㅊ' if nv(2) else '치',
                'ch → ㅊ/치 [제1절 1항]')
            i += 2; continue

        if rest.startswith('sh'):
            add('ㅅ' if nv(2) else '시',
                'sh → ㅅ/시 [제1절 1항: sh는 뒤따르는 모음과 합쳐 시/샤/셔 등으로 표기]')
            i += 2; continue

        if rest.startswith('ph'):
            add('ㅍ' if nv(2) else '프',
                'ph → ㅍ (모음 앞) / 프 (자음 앞·어말) [제1절 1항: ph는 f음]')
            i += 2; continue

        if rest.startswith('th'):
            add('ㅅ' if nv(2) else '스',
                'th → ㅅ/스 [제1절 1항: 무성 치음 [θ]는 ㅅ으로 표기]')
            i += 2; continue

        if rest.startswith('wh') and i == 0:
            add('ㅎ', 'wh → ㅎ (어두) [제1절 1항]')
            i += 2; continue

        if rest.startswith('kn') and i == 0:
            add('ㄴ', 'kn → ㄴ (어두 k 묵음) [제1절 1항]')
            i += 2; continue

        if rest.startswith('gn') and i == 0:
            add('ㄴ', 'gn → ㄴ (어두 g 묵음)')
            i += 2; continue

        if rest.startswith('qu'):
            add('ㅋ', 'qu → ㅋ [qu는 [kw]음, w는 다음 모음과 합침]')
            i += 2; continue

        if rest.startswith('ng'):
            if i + 2 < n and is_v(ch(2)):
                add('ㅇ', 'ng → ㅇ [제1절 1항: ng는 ㅇ으로, 뒤 모음과 결합]')
            else:
                add('ㅇ', 'ng → ㅇ (어말·자음 앞) [제1절 1항]')
            i += 2; continue

        if rest.startswith('nk'):
            add('ㅇ크', 'nk → ㅇ크 [nk는 [ŋk]]')
            i += 2; continue

        # ── 모음 2자 패턴 ──
        if rest.startswith('oo'):
            add('우', 'oo → 우 [제1절 2항 모음 일람]'); i += 2; continue
        if rest.startswith('ou') or rest.startswith('ow'):
            add('아우', f'{rest[:2]} → 아우 [제1절 2항: [aʊ] 발음]'); i += 2; continue
        if rest.startswith('oi') or rest.startswith('oy'):
            add('오이', f'{rest[:2]} → 오이 [제1절 2항: [ɔɪ] 발음]'); i += 2; continue
        if rest.startswith('ai') or rest.startswith('ay'):
            add('에이', f'{rest[:2]} → 에이 [제1절 2항: [eɪ] 발음]'); i += 2; continue
        if rest.startswith('au') or rest.startswith('aw'):
            add('오', f'{rest[:2]} → 오 [제1절 2항: [ɔː] 발음]'); i += 2; continue
        if rest.startswith('ea'):
            add('이', 'ea → 이 [제1절 2항: [iː] 발음]'); i += 2; continue
        if rest.startswith('ee'):
            add('이', 'ee → 이 [제1절 2항: [iː] 발음]'); i += 2; continue
        if rest.startswith('ie') and i + 2 >= n:
            add('이', 'ie → 이 (어말) [제1절 2항]'); i += 2; continue
        if rest.startswith('ew') or rest.startswith('ue'):
            add('유', f'{rest[:2]} → 유 [제1절 2항: [juː] 발음]'); i += 2; continue

        # r 앞 모음 (어말·자음 앞에서만)
        if len(rest) >= 2 and rest[1] == 'r' and (i + 2 >= n or not is_v(ch(2))):
            vowel_r_map = {
                'ar': ('아', 'ar → 아 [제1절 2항: r 앞 a는 아로]'),
                'er': ('어', 'er → 어 [제1절 2항: r 앞 e는 어로]'),
                'ir': ('어', 'ir → 어 [제1절 2항: r 앞 i는 어로]'),
                'ur': ('어', 'ur → 어 [제1절 2항: r 앞 u는 어로]'),
                'or': ('오', 'or → 오 [제1절 2항: r 앞 o는 오로]'),
            }
            key = rest[:2]
            if key in vowel_r_map:
                seg, rule_text = vowel_r_map[key]
                add(seg, rule_text)
                i += 2; continue

        # ── 단일 모음 ──
        vowel_map = {
            'a': ('아', 'a → 아 [제1절 2항]'),
            'e': ('에', 'e → 에 [제1절 2항]'),
            'i': ('이', 'i → 이 [제1절 2항]'),
            'o': ('오', 'o → 오 [제1절 2항]'),
            'u': ('어', 'u → 어 [제1절 2항: 단모음 u는 어로]'),
        }
        if c in vowel_map:
            seg, rule_text = vowel_map[c]
            add(seg, rule_text)
            i += 1; continue

        # ── 단일 자음 ──
        if c == 'b':
            add('ㅂ' if nv() else '브',
                'b → ㅂ (모음 앞) / 브 (자음 앞·어말) [제1절 1항]')
        elif c == 'c':
            if ch(1) in 'eiy':
                add('ㅅ' if nv() else '스',
                    f'c → ㅅ/스 ({ch(1)} 앞: [s]음) [제1절 1항]')
            else:
                add('ㅋ' if nv() else '크',
                    'c → ㅋ (모음 앞) / 크 (자음 앞·어말) [제1절 1항]')
        elif c == 'd':
            add('ㄷ' if nv() else '드',
                'd → ㄷ (모음 앞) / 드 (자음 앞·어말) [제1절 1항]')
        elif c == 'f':
            add('ㅍ' if nv() else '프',
                'f → ㅍ (모음 앞) / 프 (자음 앞·어말) [제1절 1항]')
        elif c == 'g':
            if ch(1) in 'eiy':
                add('ㅈ' if nv() else '지',
                    f'g → ㅈ ({ch(1)} 앞: [dʒ]음) [제1절 1항]')
            else:
                add('ㄱ' if nv() else '그',
                    'g → ㄱ (모음 앞) / 그 (자음 앞·어말) [제1절 1항]')
        elif c == 'h':
            if nv() or i == 0:
                add('ㅎ', 'h → ㅎ (모음 앞·어두) [제1절 1항]')
            # else: 묵음
        elif c == 'j':
            add('ㅈ' if nv() else '즈', 'j → ㅈ/즈 [제1절 1항]')
        elif c == 'k':
            add('ㅋ' if nv() else '크',
                'k → ㅋ (모음 앞) / 크 (자음 앞·어말) [제1절 1항]')
        elif c == 'l':
            add('ㄹ' if nv() else '르',
                'l → ㄹ (모음 앞) / 르 (자음 앞·어말) [제1절 1항]')
        elif c == 'm':
            add('ㅁ', 'm → ㅁ [제1절 1항]')
        elif c == 'n':
            add('ㄴ', 'n → ㄴ [제1절 1항]')
        elif c == 'p':
            add('ㅍ' if nv() else '프',
                'p → ㅍ (모음 앞) / 프 (자음 앞·어말) [제1절 1항]')
        elif c == 'r':
            add('ㄹ' if nv() else '르',
                'r → ㄹ (모음 앞) / 르 (자음 앞·어말) [제1절 1항]')
        elif c == 's':
            if i == 0:
                add('스', 's → 스 (어두) [제1절 1항: 어두 무성음]')
            elif nv():
                add('ㅅ', 's → ㅅ (모음 앞) [제1절 1항]')
            else:
                add('스', 's → 스 (자음 앞·어말) [제1절 1항]')
        elif c == 't':
            add('ㅌ' if nv() else '트',
                't → ㅌ (모음 앞) / 트 (자음 앞·어말) [제1절 1항]')
        elif c == 'v':
            add('ㅂ' if nv() else '브',
                'v → ㅂ (모음 앞) / 브 (자음 앞·어말) [제1절 1항]')
        elif c == 'w':
            combo = {'a': '와', 'e': '웨', 'i': '위', 'o': '워', 'u': '우'}
            n2 = ch(1)
            if n2 in combo:
                add(combo[n2], f'w+{n2} → {combo[n2]} [w는 반모음, 제1절 1항]')
                i += 2; continue
            else:
                add('우', 'w → 우 [w는 반모음, 제1절 1항]')
        elif c == 'x':
            if i == 0:
                add('ㅅ', 'x → ㅅ (어두: [z]음) [제1절 1항]')
            else:
                add('ㄱㅅ' if nv() else 'ㄱ스',
                    'x → ㄱㅅ/ㄱ스 (어중·어말: [ks]음) [제1절 1항]')
        elif c == 'y':
            if i == 0:
                combo = {'a': '야', 'e': '예', 'o': '요', 'u': '유'}
                n2 = ch(1)
                if n2 in combo:
                    add(combo[n2], f'y+{n2} → {combo[n2]} [y는 반모음, 제1절 2항]')
                    i += 2; continue
            add('이', 'y → 이 [제1절 2항]')
        elif c == 'z':
            add('ㅈ' if (nv() or i == 0) else '즈',
                'z → ㅈ (어두·모음 앞) / 즈 (자음 앞·어말) [제1절 1항]')
        else:
            i += 1; continue

        i += 1

    return _assemble(segments), rules


# ── 프랑스어 표기법 ──────────────────────────────────────────────

def _transcribe_french(word):
    """
    프랑스어 → 한국어 표기
    국립국어원 외래어 표기법 제3장 제2절 프랑스어 규정 적용
    """
    w = word.lower().strip()
    # 악상 정규화
    w = w.replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e')
    w = w.replace('à', 'a').replace('â', 'a')
    w = w.replace('î', 'i').replace('ï', 'i')
    w = w.replace('ô', 'o').replace('œ', 'e').replace('æ', 'e')
    w = w.replace('û', 'u').replace('ù', 'u').replace('ü', 'u')
    w = w.replace('ç', 's')

    segments = []
    rules = []
    n = len(w)

    def ch(offset=0):
        idx = i + offset
        return w[idx] if 0 <= idx < n else ''

    def is_v(c):
        return c in 'aeiou'

    def add(seg, rule):
        segments.append(seg)
        if rule and rule not in rules:
            rules.append(rule)

    i = 0
    while i < n:
        c = ch()
        rest = w[i:]

        if rest.startswith('ch'):
            add('슈' if is_v(ch(2)) else '슈', 'ch → 슈 [프랑스어 제2절 1항]'); i += 2; continue
        if rest.startswith('gn'):
            add('ㄴ', 'gn → ㄴ [프랑스어 제2절: gn는 [ɲ]]'); i += 2; continue
        if rest.startswith('qu'):
            add('ㅋ', 'qu → ㅋ [프랑스어 제2절]'); i += 2; continue
        if rest.startswith('oi'):
            add('우아', 'oi → 우아 [프랑스어 제2절: [wa] 발음]'); i += 2; continue
        if rest.startswith('ou'):
            add('우', 'ou → 우 [프랑스어 제2절: [u] 발음]'); i += 2; continue
        if rest.startswith('au') or rest.startswith('eau'):
            step = 3 if rest.startswith('eau') else 2
            add('오', f'{rest[:step]} → 오 [프랑스어 제2절: [o] 발음]'); i += step; continue
        if rest.startswith('ai') or rest.startswith('ei'):
            add('에', f'{rest[:2]} → 에 [프랑스어 제2절: [ɛ] 발음]'); i += 2; continue
        if c == 'e' and i == n - 1:
            # 어말 무음 e
            i += 1; continue

        # 어말 묵음 자음
        if i == n - 1 and c in 'tsxzd' and not is_v(ch(-1)):
            rules.append(f'어말 {c} 묵음 [프랑스어 제2절: 어말 자음은 발음하지 않는 경우가 많음]')
            i += 1; continue

        # 기본: 영어 규칙 공유 부분
        if c in 'aeiou':
            vmap = {'a': '아', 'e': '에', 'i': '이', 'o': '오', 'u': '위'}
            add(vmap[c], f'{c} → {vmap[c]} [프랑스어 제2절 모음 규정]')
        elif c == 'r':
            add('르' if i == n - 1 else 'ㄹ', 'r → ㄹ/르 [프랑스어 제2절]')
        elif c == 'l':
            add('ㄹ' if is_v(ch(1)) else '르', 'l → ㄹ/르 [프랑스어 제2절]')
        elif c == 'j':
            add('ㅈ' if is_v(ch(1)) else '주', 'j → ㅈ [프랑스어 제2절: [ʒ]음은 ㅈ]')
        elif c == 'g' and ch(1) in 'ei':
            add('ㅈ' if is_v(ch(1)) else '주', 'g → ㅈ (e/i 앞) [프랑스어 제2절: [ʒ]음]')
        elif c == 'n':
            add('ㄴ', 'n → ㄴ [프랑스어 제2절]')
        elif c == 'm':
            add('ㅁ', 'm → ㅁ [프랑스어 제2절]')
        elif c == 'p':
            add('ㅍ' if is_v(ch(1)) else '프', 'p → ㅍ/프 [프랑스어 제2절]')
        elif c == 'b':
            add('ㅂ' if is_v(ch(1)) else '브', 'b → ㅂ/브 [프랑스어 제2절]')
        elif c == 'd':
            add('ㄷ' if is_v(ch(1)) else '드', 'd → ㄷ/드 [프랑스어 제2절]')
        elif c == 'f':
            add('ㅍ' if is_v(ch(1)) else '프', 'f → ㅍ/프 [프랑스어 제2절]')
        elif c == 's':
            add('ㅅ' if is_v(ch(1)) else '스', 's → ㅅ/스 [프랑스어 제2절]')
        elif c == 't':
            add('ㅌ' if is_v(ch(1)) else '트', 't → ㅌ/트 [프랑스어 제2절]')
        elif c == 'v':
            add('ㅂ' if is_v(ch(1)) else '브', 'v → ㅂ/브 [프랑스어 제2절]')
        elif c == 'k':
            add('ㅋ' if is_v(ch(1)) else '크', 'k → ㅋ/크 [프랑스어 제2절]')
        elif c == 'c':
            if ch(1) in 'ei':
                add('ㅅ' if is_v(ch(1)) else '스', 'c → ㅅ (e/i 앞) [프랑스어 제2절]')
            else:
                add('ㅋ' if is_v(ch(1)) else '크', 'c → ㅋ/크 [프랑스어 제2절]')
        else:
            pass

        i += 1

    return _assemble(segments), rules


# ── 독일어 표기법 ──────────────────────────────────────────────

def _transcribe_german(word):
    """
    독일어 → 한국어 표기
    국립국어원 외래어 표기법 제3장 제3절 독일어 규정 적용
    """
    w = word.lower().strip()
    w = w.replace('ä', 'e').replace('ö', 'o').replace('ü', 'u').replace('ß', 'ss')

    segments = []
    rules = []
    n = len(w)

    def ch(offset=0):
        idx = i + offset
        return w[idx] if 0 <= idx < n else ''

    def is_v(c):
        return c in 'aeiou'

    def add(seg, rule):
        segments.append(seg)
        if rule and rule not in rules:
            rules.append(rule)

    i = 0
    while i < n:
        c = ch()
        rest = w[i:]

        if rest.startswith('sch'):
            add('슈', 'sch → 슈 [독일어 제3절 1항: [ʃ]음]'); i += 3; continue
        if rest.startswith('ch'):
            add('ㅎ' if is_v(ch(2)) else '흐', 'ch → ㅎ/흐 [독일어 제3절 1항: [x] 또는 [ç]음]')
            i += 2; continue
        if rest.startswith('qu'):
            add('ㅋ', 'qu → ㅋ [독일어 제3절]'); i += 2; continue
        if rest.startswith('ei'):
            add('아이', 'ei → 아이 [독일어 제3절 2항: [aɪ] 발음]'); i += 2; continue
        if rest.startswith('eu') or rest.startswith('äu'):
            add('오이', f'{rest[:2]} → 오이 [독일어 제3절 2항: [ɔɪ] 발음]'); i += 2; continue
        if rest.startswith('ie'):
            add('이', 'ie → 이 [독일어 제3절 2항: [iː] 발음]'); i += 2; continue
        if rest.startswith('au'):
            add('아우', 'au → 아우 [독일어 제3절 2항: [aʊ] 발음]'); i += 2; continue
        if rest.startswith('ss') or rest.startswith('ß'):
            step = 2 if rest.startswith('ss') else 1
            add('ㅅ' if is_v(ch(step)) else '스',
                'ss/ß → ㅅ/스 [독일어 제3절 1항]')
            i += step; continue
        if c == 'z':
            add('ㅊ' if is_v(ch(1)) else '츠', 'z → ㅊ/츠 [독일어 제3절 1항: [ts]음]')
        elif c == 'w':
            add('ㅂ' if is_v(ch(1)) else '브', 'w → ㅂ/브 [독일어 제3절 1항: [v]음]')
        elif c == 'v':
            add('ㅍ' if is_v(ch(1)) else '프', 'v → ㅍ/프 [독일어 제3절 1항: 어두 [f]음]')
        elif c == 'j':
            add('ㅇ' if is_v(ch(1)) else '이', 'j → ㅇ/이 [독일어 제3절 1항: [j]반모음]')
        elif c in 'aeiou':
            vmap = {'a': '아', 'e': '에', 'i': '이', 'o': '오', 'u': '우'}
            add(vmap[c], f'{c} → {vmap[c]} [독일어 제3절 2항 모음 규정]')
        elif c == 'r':
            add('ㄹ' if is_v(ch(1)) else '르', 'r → ㄹ/르 [독일어 제3절 1항]')
        elif c == 'l':
            add('ㄹ' if is_v(ch(1)) else '르', 'l → ㄹ/르 [독일어 제3절 1항]')
        elif c == 'n':
            add('ㄴ', 'n → ㄴ [독일어 제3절 1항]')
        elif c == 'm':
            add('ㅁ', 'm → ㅁ [독일어 제3절 1항]')
        elif c == 'p':
            add('ㅍ' if is_v(ch(1)) else '프', 'p → ㅍ/프 [독일어 제3절 1항]')
        elif c == 'b':
            add('ㅂ' if is_v(ch(1)) else '브', 'b → ㅂ/브 [독일어 제3절 1항]')
        elif c == 'd':
            add('ㄷ' if is_v(ch(1)) else '트', 'd → ㄷ/트 [독일어 제3절 1항: 어말 d는 트]')
        elif c == 'f':
            add('ㅍ' if is_v(ch(1)) else '프', 'f → ㅍ/프 [독일어 제3절 1항]')
        elif c == 's':
            if is_v(ch(1)):
                add('ㅈ', 's → ㅈ (모음 앞) [독일어 제3절 1항: 어중 모음 앞 s는 [z]]')
            else:
                add('스' if i == n - 1 else 'ㅅ', 's → ㅅ/스 [독일어 제3절 1항]')
        elif c == 't':
            add('ㅌ' if is_v(ch(1)) else '트', 't → ㅌ/트 [독일어 제3절 1항]')
        elif c == 'k':
            add('ㅋ' if is_v(ch(1)) else '크', 'k → ㅋ/크 [독일어 제3절 1항]')
        elif c == 'g':
            add('ㄱ' if is_v(ch(1)) else '크', 'g → ㄱ/크 [독일어 제3절 1항: 어말 g는 크]')
        elif c == 'h':
            if is_v(ch(1)):
                add('ㅎ', 'h → ㅎ (모음 앞) [독일어 제3절 1항]')
            # else: 묵음 또는 장모음 표시

        i += 1

    return _assemble(segments), rules


# ── 스페인어·기타 ──────────────────────────────────────────────

def _transcribe_spanish(word):
    """스페인어 → 한국어 (외래어 표기법 제3장 제4절)"""
    w = word.lower()
    w = w.replace('á', 'a').replace('é', 'e').replace('í', 'i')
    w = w.replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')

    segments = []
    rules = []
    n = len(w)

    def ch(offset=0):
        idx = i + offset
        return w[idx] if 0 <= idx < n else ''

    def is_v(c):
        return c in 'aeiou'

    def add(seg, rule):
        segments.append(seg)
        if rule and rule not in rules:
            rules.append(rule)

    i = 0
    while i < n:
        c = ch()
        rest = w[i:]

        if rest.startswith('ll'):
            add('ㅇ' if is_v(ch(2)) else '이', 'll → ㅇ/이 [스페인어 제4절: ll은 [j]음]')
            i += 2; continue
        if rest.startswith('ch'):
            add('ㅊ' if is_v(ch(2)) else '치', 'ch → ㅊ/치 [스페인어 제4절]')
            i += 2; continue
        if rest.startswith('qu'):
            add('ㅋ', 'qu → ㅋ [스페인어 제4절]'); i += 2; continue
        if rest.startswith('rr'):
            add('ㄹ' if is_v(ch(2)) else '르', 'rr → ㄹ/르 [스페인어 강조 r]')
            i += 2; continue

        if c == 'j' or (c == 'g' and ch(1) in 'ei'):
            add('ㅎ' if is_v(ch(1)) else '흐',
                f'{c} → ㅎ/흐 [스페인어 제4절: [x]음은 ㅎ]')
        elif c == 'v':
            add('ㅂ' if is_v(ch(1)) else '브', 'v → ㅂ/브 [스페인어 제4절: b와 동음]')
        elif c == 'z' or (c == 'c' and ch(1) in 'ei'):
            add('ㅅ' if is_v(ch(1)) else '스',
                f'{c} → ㅅ/스 [스페인어 제4절: [s]음]')
        elif c in 'aeiou':
            vmap = {'a': '아', 'e': '에', 'i': '이', 'o': '오', 'u': '우'}
            add(vmap[c], f'{c} → {vmap[c]} [스페인어 제4절 모음 규정]')
        elif c == 'r':
            add('ㄹ' if is_v(ch(1)) else '르', 'r → ㄹ/르 [스페인어 제4절]')
        elif c == 'l':
            add('ㄹ' if is_v(ch(1)) else '르', 'l → ㄹ/르 [스페인어 제4절]')
        elif c == 'n':
            add('ㄴ', 'n → ㄴ');
        elif c == 'm':
            add('ㅁ', 'm → ㅁ')
        elif c == 'p':
            add('ㅍ' if is_v(ch(1)) else '프', 'p → ㅍ/프 [스페인어 제4절]')
        elif c == 'b':
            add('ㅂ' if is_v(ch(1)) else '브', 'b → ㅂ/브 [스페인어 제4절]')
        elif c == 'd':
            add('ㄷ' if is_v(ch(1)) else '드', 'd → ㄷ/드 [스페인어 제4절]')
        elif c == 'f':
            add('ㅍ' if is_v(ch(1)) else '프', 'f → ㅍ/프 [스페인어 제4절]')
        elif c == 's':
            add('ㅅ' if is_v(ch(1)) else '스', 's → ㅅ/스 [스페인어 제4절]')
        elif c == 't':
            add('ㅌ' if is_v(ch(1)) else '트', 't → ㅌ/트 [스페인어 제4절]')
        elif c == 'k':
            add('ㅋ' if is_v(ch(1)) else '크', 'k → ㅋ/크')
        elif c == 'g':
            add('ㄱ' if is_v(ch(1)) else '그', 'g → ㄱ/그 [스페인어 제4절]')
        elif c == 'h':
            pass  # 스페인어 h는 묵음
        elif c == 'y':
            add('ㅇ' if is_v(ch(1)) else '이', 'y → ㅇ/이 [스페인어 제4절: [j]음]')
        elif c == 'x':
            add('ㄱㅅ' if is_v(ch(1)) else 'ㄱ스', 'x → ㄱㅅ/ㄱ스 [스페인어 제4절]')

        i += 1

    return _assemble(segments), rules


# ── 공개 API ─────────────────────────────────────────────────────

_LANG_NAMES = {'en': '영어', 'fr': '프랑스어', 'de': '독일어', 'es': '스페인어', 'pt': '포르투갈어'}
_LANG_SECTION = {'en': '제1절', 'fr': '제2절', 'de': '제3절', 'es': '제4절'}

def suggest(original, language=None):
    """
    원어 철자를 외래어 표기법에 따라 한국어로 변환하고 적용 규칙을 반환.

    Args:
        original: 원어 철자 (예: "Leonor Antunes")
        language: 언어 코드 ('en','fr','de','es') — None이면 자동 감지

    Returns:
        {
          'transcription': '레오노르 안투네스',
          'rules': ['l → ㄹ (모음 앞) [제1절 1항]', ...],
          'language': 'en',
          'language_name': '영어',
          'section': '제1절',
          'note': '규칙 기반 제안 (용례 미등록 단어)'
        }
        또는 None (original이 없거나 알파벳이 없을 때)
    """
    if not original:
        return None
    if not re.search(r'[a-zA-ZÀ-ÿ]', original):
        return None

    lang = language or detect_language(original)

    fn_map = {
        'en': _transcribe_english,
        'fr': _transcribe_french,
        'de': _transcribe_german,
        'es': _transcribe_spanish,
    }

    # 언어 감지 실패
    if lang is None:
        return {
            'transcription': None,
            'rules': [],
            'language': None,
            'language_name': None,
            'section': None,
            'note': '언어를 특정할 수 없어 표기 제안을 드릴 수 없습니다.',
        }

    # 언어는 감지됐지만 표기법 규칙 미구현
    if lang not in fn_map:
        lang_name = _LANG_NAMES.get(lang, lang)
        return {
            'transcription': None,
            'rules': [],
            'language': lang,
            'language_name': lang_name,
            'section': None,
            'note': f'{lang_name} 표기법 규칙이 구현되지 않아 표기 제안을 드릴 수 없습니다.',
        }

    fn = fn_map[lang]
    parts = original.split()
    trans_parts, all_rules = [], []
    for part in parts:
        t, r = fn(part)
        trans_parts.append(t)
        for rule in r:
            if rule not in all_rules:
                all_rules.append(rule)

    return {
        'transcription': ' '.join(trans_parts),
        'rules': all_rules,
        'language': lang,
        'language_name': _LANG_NAMES.get(lang, lang),
        'section': _LANG_SECTION.get(lang, ''),
        'note': '규칙 기반 제안 (국립국어원 용례 미등록 단어)',
    }

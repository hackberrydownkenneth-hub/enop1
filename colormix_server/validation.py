"""利用登録の入力チェック。

ブラウザ側 (`colormix/profile.js`) と同じルールをサーバーでも必ず適用する。
クライアントの検証は入力補助であって、信用の根拠にはしない。
"""

from __future__ import annotations

import re

AFFILIATIONS = ("salon", "freelance")
LANGUAGES = ("ja", "yue")
SALON_MAX = 80
_HANDLE_RE = re.compile(r"^[a-z0-9._]{1,30}$")
_URL_RE = re.compile(r"instagram\.com/([^/?#]+)", re.IGNORECASE)

# 明らかに実在しない入力（123 / 111 / test など）を弾くための決まり。
# Instagram の実在確認まではできないので、まず本物ではないものだけを落とす。
HANDLE_MIN = 3
JUNK_HANDLES = frozenset(
    """
    abc abcd abcde asd asdf asdfgh qwe qwer qwerty
    test tester testing tests sample example demo dummy
    none nothing null nil nan unknown anonymous anon
    user users guest hello hi hey me you my mine
    ig insta instagram private secret no nope yes ok
    aaa bbb ccc xxx yyy zzz www qaz zxc
    """.split()
)


def _is_repeated(text: str) -> bool:
    """「111」「aaaa」のように1文字の繰り返しか。"""
    return len(set(text)) == 1


def _is_sequential(text: str) -> bool:
    """「123」「abcd」のような連番か。"""
    if len(text) < 3:
        return False
    diffs = {ord(b) - ord(a) for a, b in zip(text, text[1:])}
    return diffs in ({1}, {-1})


def looks_fake(handle: str) -> bool:
    """形は正しくても中身が明らかにでたらめなら True。"""
    if not handle:
        return False
    if len(handle) < HANDLE_MIN:
        return True
    # 記号だけ、数字だけは実在アカウントとして扱わない
    if not re.search(r"[a-z]", handle):
        return True
    if _is_repeated(handle) or _is_sequential(handle):
        return True
    if handle in JUNK_HANDLES:
        return True
    # Instagram は先頭・末尾のピリオド、ピリオドの連続を認めていない
    return handle.startswith(".") or handle.endswith(".") or ".." in handle


def normalize_instagram(raw: object) -> str:
    """入力された Instagram アカウントを ID だけに揃える。

    "@Foo_Bar" も "https://www.instagram.com/foo.bar/?hl=ja" も "foo.bar" になる。
    """
    text = ("" if raw is None else str(raw)).strip()
    if not text:
        return ""

    match = _URL_RE.search(text)
    if match:
        text = match.group(1)
    else:
        text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
        text = text.lstrip("@")
        text = re.split(r"[/?#]", text)[0]

    return text.strip().lstrip("@").lower()


class ValidationError(ValueError):
    """入力が受け付けられないときに投げる。`code` は画面側の文言キーと対応する。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_registration(payload: object) -> dict:
    """登録リクエストを検証して、保存できる形に整える。

    :raises ValidationError: 入力が不正なとき
    """
    data = payload if isinstance(payload, dict) else {}

    affiliation = data.get("affiliation")
    if affiliation not in AFFILIATIONS:
        raise ValidationError("affiliation")

    # サロン所属なら店名は必須
    salon = ""
    if affiliation == "salon":
        salon = ("" if data.get("salon") is None else str(data["salon"])).strip()[:SALON_MAX]
        if not salon:
            raise ValidationError("salon")

    instagram = normalize_instagram(data.get("instagram"))
    if not instagram:
        raise ValidationError("instagram")
    if not _HANDLE_RE.match(instagram):
        raise ValidationError("instagram_format")
    if looks_fake(instagram):
        raise ValidationError("instagram_fake")

    lang = data.get("lang")
    if lang not in LANGUAGES:
        lang = ""

    return {
        "affiliation": affiliation,
        "salon": salon,
        "instagram": instagram,
        "lang": lang,
    }

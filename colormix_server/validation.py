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

    instagram = normalize_instagram(data.get("instagram"))
    if not instagram:
        raise ValidationError("instagram")
    if not _HANDLE_RE.match(instagram):
        raise ValidationError("instagram_format")

    salon = ""
    if affiliation == "salon":
        salon = ("" if data.get("salon") is None else str(data["salon"])).strip()[:SALON_MAX]

    lang = data.get("lang")
    if lang not in LANGUAGES:
        lang = ""

    return {
        "affiliation": affiliation,
        "salon": salon,
        "instagram": instagram,
        "lang": lang,
    }

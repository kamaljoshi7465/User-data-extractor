import string
from typing import List, Optional


def generate_all_alphabet_patterns(
    allowed_second_chars: Optional[str] = None
) -> List[str]:
    """
    Generates all 676 two-letter combinations across A-Z:
    Aa%, Ab%, ..., Az%,
    Ba%, Bb%, ..., Bz%,
    ...
    Za%, Zb%, ..., Zz%
    """
    second_chars = allowed_second_chars if allowed_second_chars is not None else string.ascii_lowercase
    patterns: List[str] = []
    for first_ch in string.ascii_uppercase:
        for second_ch in second_chars:
            patterns.append(f"{first_ch}{second_ch}%")
    return patterns


def generate_first_name_patterns(
    prefix: str = "ALL",
    allowed_chars: Optional[str] = None
) -> List[str]:
    """
    Generates search patterns with wildcards.

    If prefix='ALL' or 'A-Z', produces all 676 patterns across all letters:
    ['Aa%', ..., 'Az%', 'Ba%', ..., 'Bz%', ..., 'Za%', ..., 'Zz%']

    If prefix is a single letter (e.g. 'A'):
    ['Aa%', 'Ab%', 'Ac%', ..., 'Az%']

    If prefix is a custom string (e.g. 'Sm'):
    ['Sma%', 'Smb%', ..., 'Smz%']
    """
    clean_prefix = prefix.strip() if prefix else "ALL"
    if clean_prefix.upper() in ("ALL", "A-Z", "*"):
        return generate_all_alphabet_patterns(allowed_second_chars=allowed_chars)

    chars = allowed_chars if allowed_chars is not None else string.ascii_lowercase
    formatted_prefix = clean_prefix[0].upper() + clean_prefix[1:].lower()
    return [f"{formatted_prefix}{ch}%" for ch in chars]


def generate_sub_patterns(pattern: str, allowed_chars: Optional[str] = None) -> List[str]:
    """
    Expands an existing pattern into finer sub-patterns if the external server
    indicates that the result set is still too large.

    Example:
        'Aa%' -> ['Aaa%', 'Aab%', ..., 'Aaz%']
    """
    chars = allowed_chars if allowed_chars is not None else string.ascii_lowercase
    base = pattern.rstrip("%")
    return [f"{base}{ch}%" for ch in chars]


def build_search_payload(
    first_name: str,
    last_name: str = "%%",
    captcha_token: str = "",
    antiforgery_token: str = ""
) -> dict:
    """
    Constructs the form-urlencoded dictionary required by the external ARRT endpoint.
    """
    payload = {
        "firstName": first_name,
        "lastName": last_name,
    }
    if captcha_token:
        payload["captchaSuccessCode"] = captcha_token

    if antiforgery_token:
        payload["__RequestVerificationToken"] = antiforgery_token

    return payload

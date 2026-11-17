import pytest
from app.utils.pattern_generator import (
    generate_first_name_patterns,
    generate_all_alphabet_patterns,
    generate_sub_patterns,
    build_search_payload,
)


def test_default_all_prefixes_generates_676():
    patterns = generate_first_name_patterns("ALL")
    assert len(patterns) == 676
    # Starts with Aa..Az
    assert patterns[0] == "Aa%"
    assert patterns[25] == "Az%"
    # Continues with Ba..Bz
    assert patterns[26] == "Ba%"
    assert patterns[51] == "Bz%"
    # Ends with Za..Zz
    assert patterns[-26] == "Za%"
    assert patterns[-1] == "Zz%"


def test_single_a_prefix_patterns():
    patterns = generate_first_name_patterns("A")
    assert len(patterns) == 26
    assert patterns[0] == "Aa%"
    assert patterns[1] == "Ab%"
    assert patterns[2] == "Ac%"
    assert patterns[-1] == "Az%"


def test_custom_prefix_patterns():
    b_patterns = generate_first_name_patterns("B")
    assert len(b_patterns) == 26
    assert b_patterns[0] == "Ba%"
    assert b_patterns[-1] == "Bz%"

    z_patterns = generate_first_name_patterns("Z")
    assert len(z_patterns) == 26
    assert z_patterns[0] == "Za%"
    assert z_patterns[-1] == "Zz%"


def test_allowed_chars_subset():
    patterns = generate_first_name_patterns("A", allowed_chars="abc")
    assert patterns == ["Aa%", "Ab%", "Ac%"]


def test_sub_pattern_expansion():
    sub = generate_sub_patterns("Aa%", allowed_chars="ab")
    assert sub == ["Aaa%", "Aab%"]


def test_build_search_payload():
    payload = build_search_payload(
        first_name="Aa%",
        last_name="%%",
        captcha_token="test_captcha_123",
        antiforgery_token="test_csrf_456"
    )
    assert payload["firstName"] == "Aa%"
    assert payload["lastName"] == "%%"
    assert payload["captchaSuccessCode"] == "test_captcha_123"
    assert payload["__RequestVerificationToken"] == "test_csrf_456"

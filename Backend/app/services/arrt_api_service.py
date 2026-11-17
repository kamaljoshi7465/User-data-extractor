import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from app.config import Settings, get_settings
from app.utils.pattern_generator import build_search_payload

logger = logging.getLogger("arrt_extractor.api")


class ArrtApiException(Exception):
    """Base exception for ARRT external API interactions."""
    pass


class CaptchaOrAuthError(ArrtApiException):
    """Raised when CAPTCHA token, antiforgery token, or session cookies are invalid or expired."""
    pass


class ServerOverloadedError(ArrtApiException):
    """Raised when the external server responds with 429 (Too Many Requests) or 503 (Overloaded)."""
    pass


class TransientApiError(ArrtApiException):
    """Raised for transient issues (timeouts, connection errors, 502/504 gateways) suitable for retry."""
    pass


class InvalidResponseError(ArrtApiException):
    """Raised when the external API returns an unexpected HTML error page or malformed JSON."""
    pass


def flatten_record(data: Dict[str, Any], parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """
    Recursively flattens nested dictionaries and structures into a single-level dictionary.
    
    Examples:
        {"name": {"first": "Kamal", "last": "Joshi"}} -> {"name_first": "Kamal", "name_last": "Joshi"}
        {"credentials": ["R", "CT"]} -> {"credentials": "R; CT"}
        {"meta": [{"code": "A"}, {"code": "B"}]} -> {"meta": '[{"code": "A"}, {"code": "B"}]'}
    """
    items: Dict[str, Any] = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key

        if isinstance(value, dict):
            items.update(flatten_record(value, new_key, sep=sep))
        elif isinstance(value, list):
            if all(isinstance(elem, (str, int, float, bool)) for elem in value):
                # Join simple primitive lists with semicolon
                items[new_key] = "; ".join(str(elem) for elem in value)
            else:
                # Complex list of objects: serialize to readable JSON string
                items[new_key] = json.dumps(value, ensure_ascii=False)
        else:
            items[new_key] = value

    return items


class ArrtApiService:
    """
    Service responsible for interacting with the external ARRT verification API.
    Handles authentication headers, form encoding, timeout control, retries,
    and adaptive response parsing.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self.settings = settings or get_settings()
        self._external_client = client

    def _get_headers(self) -> Dict[str, str]:
        """Constructs browser-like HTTP request headers."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.arrt.org",
            "Referer": "https://www.arrt.org/pages/verify-credentials",
        }
        if self.settings.arrt_cookie:
            headers["Cookie"] = self.settings.arrt_cookie
        if self.settings.arrt_antiforgery_token:
            headers["RequestVerificationToken"] = self.settings.arrt_antiforgery_token

        return headers

    async def fetch_users_by_pattern(
        self,
        first_name_pattern: str,
        last_name_pattern: str = "%%",
        client: Optional[httpx.AsyncClient] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes a single search request for the given pattern with controlled retries
        and comprehensive error categorization.
        """
        # Note: Antiforgery token is passed via 'RequestVerificationToken' header as required by ASP.NET Core
        payload = build_search_payload(
            first_name=first_name_pattern,
            last_name=last_name_pattern,
            captcha_token=self.settings.arrt_captcha_token,
            antiforgery_token="",
        )

        headers = self._get_headers()
        url = self.settings.arrt_api_url
        timeout = httpx.Timeout(self.settings.request_timeout)

        use_client = client or self._external_client

        # If no client was injected, open a short-lived one
        if use_client is not None:
            return await self._execute_request_with_retry(
                client=use_client,
                url=url,
                payload=payload,
                headers=headers,
                timeout=timeout,
                pattern=first_name_pattern,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as temp_client:
                return await self._execute_request_with_retry(
                    client=temp_client,
                    url=url,
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                    pattern=first_name_pattern,
                )

    async def _execute_request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Dict[str, str],
        headers: Dict[str, str],
        timeout: httpx.Timeout,
        pattern: str,
    ) -> List[Dict[str, Any]]:
        """
        Performs the HTTP POST call with exponential backoff for transient issues.
        Fails fast on CAPTCHA, authorization, and 429/503 overload conditions.
        """
        attempt = 0
        max_retries = self.settings.max_retries
        backoff = self.settings.backoff_factor

        while attempt <= max_retries:
            attempt += 1
            try:
                response = await client.post(
                    url,
                    data=payload,
                    headers=headers,
                    timeout=timeout,
                )

                # 1. Overload / Rate Limit Checks
                if response.status_code in (429, 503):
                    logger.warning(
                        f"External server overloaded (HTTP {response.status_code}) for pattern '{pattern}'"
                    )
                    raise ServerOverloadedError(
                        f"External server responded with HTTP {response.status_code} (Service Overloaded / Rate Limited)."
                    )

                # 2. Authorization / CAPTCHA failures
                if response.status_code in (401, 403):
                    logger.error(
                        f"External server rejected authentication or CAPTCHA (HTTP {response.status_code}) for pattern '{pattern}'"
                    )
                    raise CaptchaOrAuthError(
                        f"External API authentication / CAPTCHA failed (HTTP {response.status_code})."
                    )

                # 3. Server errors / CAPTCHA failure error pages
                if response.status_code == 500:
                    resp_lower = response.text.lower()
                    if "unhandled error has occurred" in resp_lower or "error - arrt" in resp_lower:
                        logger.error(
                            f"External server returned unhandled HTTP 500 error page for pattern '{pattern}'. "
                            f"This indicates that the CAPTCHA token was already consumed/expired, or session credentials mismatch."
                        )
                        raise CaptchaOrAuthError(
                            "External ARRT server returned HTTP 500 (Unhandled Server Error). "
                            "The CAPTCHA token has already been consumed/expired or session tokens are invalid."
                        )

                if response.status_code in (500, 502, 504):
                    if attempt <= max_retries:
                        sleep_time = backoff * (2 ** (attempt - 1))
                        logger.warning(
                            f"Transient HTTP {response.status_code} for pattern '{pattern}' "
                            f"(attempt {attempt}/{max_retries + 1}). Retrying in {sleep_time:.1f}s..."
                        )
                        await asyncio.sleep(sleep_time)
                        continue
                    else:
                        raise TransientApiError(
                            f"External server returned persistent HTTP {response.status_code} after {attempt} attempts."
                        )

                # 4. Check for client errors (400)
                if response.status_code >= 400:
                    raise ArrtApiException(
                        f"External API returned HTTP {response.status_code}: {response.text[:200]}"
                    )

                # 5. Parse response content
                return self._parse_api_response(response, pattern)

            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                if attempt <= max_retries:
                    sleep_time = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f"Network/timeout error for pattern '{pattern}': {exc!r} "
                        f"(attempt {attempt}/{max_retries + 1}). Retrying in {sleep_time:.1f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                else:
                    logger.error(f"Pattern '{pattern}' failed after {attempt} attempts: {exc!r}")
                    raise TransientApiError(
                        f"Network timeout / connection error after {attempt} attempts: {str(exc)}"
                    ) from exc

        # Should never reach here, but for safety:
        raise TransientApiError(f"Pattern '{pattern}' exceeded maximum retry attempts.")

    def _parse_api_response(self, response: httpx.Response, pattern: str) -> List[Dict[str, Any]]:
        """
        Parses ARRT HTML table or JSON responses.
        Extracts user records, credential details, and tokens.
        """
        raw_text = response.text.strip()
        if not raw_text:
            logger.info(f"Empty response body received for pattern '{pattern}'.")
            return []

        lower_text = raw_text.lower()

        # Check for CAPTCHA or Anti-forgery failure blocks in HTML or text
        if "cf-browser-verification" in lower_text or "recaptcha" in lower_text or "g-recaptcha" in lower_text:
            raise CaptchaOrAuthError("External API returned CAPTCHA challenge HTML instead of data.")
        if "request verification token" in lower_text and ("the required anti-forgery" in lower_text or "antiforgery" in lower_text):
            raise CaptchaOrAuthError("External API rejected antiforgery token.")

        # 1. Parse ARRT HTML Table response
        if "<table" in lower_text or "verifycredentialslist" in lower_text:
            return self._parse_html_table(raw_text, pattern)

        # 2. Parse JSON response (fallback or for mocked tests)
        if raw_text.startswith("{") or raw_text.startswith("["):
            try:
                parsed = response.json()
            except Exception as json_err:
                raise InvalidResponseError(
                    f"Failed to parse JSON response for pattern '{pattern}': {json_err}"
                ) from json_err

            # Check for CAPTCHA failure message inside JSON response
            if isinstance(parsed, dict):
                if parsed.get("success") is False:
                    msg = parsed.get("message") or parsed.get("error") or "Unknown external error"
                    if "captcha" in str(msg).lower():
                        raise CaptchaOrAuthError(f"External API CAPTCHA validation failed: {msg}")
                    raise ArrtApiException(f"External API indicated failure: {msg}")

                if "captchaFailed" in parsed and parsed["captchaFailed"]:
                    raise CaptchaOrAuthError("External API reported CAPTCHA validation failure.")

                # Look for records inside common wrapper keys
                for candidate_key in ["data", "records", "results", "users", "items", "rows"]:
                    if candidate_key in parsed and isinstance(parsed[candidate_key], list):
                        return [flatten_record(item) if isinstance(item, dict) else {"value": item} for item in parsed[candidate_key]]

                # If the dict itself has fields representing a single user record
                if any(k in parsed for k in ["id", "firstName", "lastName", "name"]):
                    return [flatten_record(parsed)]

                logger.info(f"Pattern '{pattern}' returned dictionary with no user records list: {list(parsed.keys())}")
                return []

            elif isinstance(parsed, list):
                records: List[Dict[str, Any]] = []
                for item in parsed:
                    if isinstance(item, dict):
                        records.append(flatten_record(item))
                    else:
                        records.append({"value": item})
                return records

        # If it's another unrecognized HTML or text page
        if raw_text.startswith("<") or "<html" in lower_text:
            raise InvalidResponseError(
                f"External API returned an unexpected HTML page: {raw_text[:200]}..."
            )

        raise InvalidResponseError(f"Unexpected response format received for pattern '{pattern}'.")

    def _parse_html_table(self, html_content: str, pattern: str) -> List[Dict[str, Any]]:
        """
        Parses the ARRT HTML table snippet containing #grid, <thead>, and <tbody>.
        Extracts Name, City, State, Credential String, and unique detail_token.
        """
        records: List[Dict[str, Any]] = []

        # Extract <tbody> content
        tbody_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", html_content, re.DOTALL | re.IGNORECASE)
        if not tbody_match:
            logger.info(f"Pattern '{pattern}' HTML returned no <tbody> section.")
            return []

        tbody_content = tbody_match.group(1).strip()
        if not tbody_content or "no data available" in tbody_content.lower() or "no matching records" in tbody_content.lower():
            logger.info(f"Pattern '{pattern}' returned empty table / no matching records.")
            return []

        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_content, re.DOTALL | re.IGNORECASE)
        for row in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
            if not tds:
                continue

            # Ignore empty table indicator row (e.g. single cell colspan)
            if len(tds) == 1 and ("no data" in tds[0].lower() or "no record" in tds[0].lower()):
                continue

            # Extract fields based on table layout
            name = re.sub(r"<[^>]+>", "", tds[0]).strip() if len(tds) > 0 else ""
            city = re.sub(r"<[^>]+>", "", tds[1]).strip() if len(tds) > 1 else ""
            state = re.sub(r"<[^>]+>", "", tds[2]).strip() if len(tds) > 2 else ""
            credential_string = re.sub(r"<[^>]+>", "", tds[3]).strip() if len(tds) > 3 else ""

            # Extract detail token from showDetails(this, 'TOKEN') onclick attribute
            detail_token = ""
            if len(tds) > 4:
                token_match = re.search(r"showDetails\(this,\s*'([^']+)'\)", tds[4])
                if token_match:
                    detail_token = token_match.group(1).strip()

            if name:
                records.append({
                    "name": name,
                    "city": city,
                    "state": state,
                    "credential_string": credential_string,
                    "detail_token": detail_token,
                })

        logger.info(f"Parsed {len(records)} records from HTML table for pattern '{pattern}'.")
        return records

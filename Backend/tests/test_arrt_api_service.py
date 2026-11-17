import httpx
import pytest
from app.config import Settings
from app.services.arrt_api_service import (
    ArrtApiService,
    CaptchaOrAuthError,
    InvalidResponseError,
    ServerOverloadedError,
    TransientApiError,
    flatten_record,
)

SAMPLE_ARRT_HTML = """
<script src="/js/custom/VerifyCredentialsList.js?v=6tasN2nLZYJl4F-a7xmFV9tHCjdAVxQzapguk2ps03c"></script>
<!-- Table -->
<div class="mobile-only">This chart displays in its entirety when browser is maximized on larger screens. Click the first column to expand/collapse the row details.</div>
<table id="grid" class="table table-striped table-bordered display compact fullwidth">
    <thead>
        <tr>
            <th class="all" data-priority="1">Name</th>
            <th>City</th>
            <th>State</th>
            <th data-priority="3">Credential String</th>
            <th class="all" data-priority="2"></th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Aadil A Esmail</td>
            <td>Spring City</td>
            <td>PA</td>
            <td>R.T.(R)(ARRT)</td>
            <td><a role="button" class="btn btn-primary allow-wrap-mobile btn-list" data-toggle="modal" data-target="#divDetailsModal" onclick="showDetails(this,'CfDJ8KZJUVg_9a9Ev8mWlQua9ZXkgvlS99SnJ_n8dmFJlRg2FiqU7CxW5hF_ld4keCmdqlOGaGY5sexrgaSALIR6u3gWpkOmQNPfYhjRI0D1VMO_O1gY-q781FJVa__65YDLJKnDJs2-9oBM420P8v3dIxZz3k7q9_xmw1qUF7urUTWOEc1_YP5-XZHjC9K9cjlckAqkeRPm2DfyvGXD2wfOxw79_kB-SVAT7ofo0Q2bU_U5M4hI0BCDAFN1NEg9Jlq7DQ');">View Details</a></td>
        </tr>
        <tr>
            <td>Aaron B Miller</td>
            <td>Philadelphia</td>
            <td>PA</td>
            <td>R.T.(R)(CT)(ARRT)</td>
            <td><a role="button" class="btn btn-primary allow-wrap-mobile btn-list" onclick="showDetails(this,'token_aaron_miller_456');">View Details</a></td>
        </tr>
    </tbody>
</table>
"""


def test_flatten_record():
    nested = {
        "id": "12345",
        "name": {"first": "Kamal", "last": "Joshi"},
        "certifications": ["Radiography", "Mammography"],
        "metadata": [{"role": "admin"}],
    }
    flattened = flatten_record(nested)
    assert flattened["id"] == "12345"
    assert flattened["name_first"] == "Kamal"
    assert flattened["name_last"] == "Joshi"
    assert flattened["certifications"] == "Radiography; Mammography"
    assert "role" in flattened["metadata"]


@pytest.mark.asyncio
async def test_successful_arrt_html_table_response():
    def handler(request: httpx.Request):
        return httpx.Response(200, text=SAMPLE_ARRT_HTML)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        records = await service.fetch_users_by_pattern("Aa%")
        assert len(records) == 2

        rec1 = records[0]
        assert rec1["name"] == "Aadil A Esmail"
        assert rec1["city"] == "Spring City"
        assert rec1["state"] == "PA"
        assert rec1["credential_string"] == "R.T.(R)(ARRT)"
        assert "CfDJ8KZJUVg" in rec1["detail_token"]

        rec2 = records[1]
        assert rec2["name"] == "Aaron B Miller"
        assert rec2["city"] == "Philadelphia"
        assert rec2["state"] == "PA"
        assert rec2["credential_string"] == "R.T.(R)(CT)(ARRT)"
        assert rec2["detail_token"] == "token_aaron_miller_456"


@pytest.mark.asyncio
async def test_empty_arrt_html_table_response():
    empty_html = """
    <table id="grid">
        <thead><tr><th>Name</th></tr></thead>
        <tbody>
            <tr><td colspan="5" class="dataTables_empty">No matching records found</td></tr>
        </tbody>
    </table>
    """

    def handler(request: httpx.Request):
        return httpx.Response(200, text=empty_html)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        records = await service.fetch_users_by_pattern("Zz%")
        assert records == []


@pytest.mark.asyncio
async def test_successful_direct_list_response():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json=[
                {"id": "101", "firstName": "Aaron", "lastName": "Smith"},
                {"id": "102", "firstName": "Abbie", "lastName": "Miller"},
            ],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        records = await service.fetch_users_by_pattern("Aa%")
        assert len(records) == 2
        assert records[0]["id"] == "101"
        assert records[1]["firstName"] == "Abbie"


@pytest.mark.asyncio
async def test_successful_wrapped_dict_response():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {"id": "201", "firstName": "Abigail", "lastName": "Brown"},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        records = await service.fetch_users_by_pattern("Ab%")
        assert len(records) == 1
        assert records[0]["id"] == "201"


@pytest.mark.asyncio
async def test_empty_api_response():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        records = await service.fetch_users_by_pattern("Az%")
        assert records == []


@pytest.mark.asyncio
async def test_captcha_failure_response():
    def handler(request: httpx.Request):
        return httpx.Response(403, text="Forbidden: Invalid CAPTCHA token")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        with pytest.raises(CaptchaOrAuthError):
            await service.fetch_users_by_pattern("Aa%")


@pytest.mark.asyncio
async def test_captcha_failure_json():
    def handler(request: httpx.Request):
        return httpx.Response(200, json={"success": False, "message": "Captcha validation failed"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        with pytest.raises(CaptchaOrAuthError):
            await service.fetch_users_by_pattern("Aa%")


@pytest.mark.asyncio
async def test_server_overloaded_429():
    def handler(request: httpx.Request):
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        with pytest.raises(ServerOverloadedError):
            await service.fetch_users_by_pattern("Aa%")


@pytest.mark.asyncio
async def test_invalid_html_response():
    def handler(request: httpx.Request):
        return httpx.Response(200, text="<html><body>Unrecognized Server Error Page</body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(client=client)
        with pytest.raises(InvalidResponseError):
            await service.fetch_users_by_pattern("Aa%")


@pytest.mark.asyncio
async def test_transient_error_retry_and_eventual_success():
    attempts = 0

    def handler(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, json=[{"id": "301", "firstName": "Adam"}])

    settings = Settings()
    settings.max_retries = 2
    settings.backoff_factor = 0.01

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = ArrtApiService(settings=settings, client=client)
        records = await service.fetch_users_by_pattern("Ad%")
        assert len(records) == 1
        assert attempts == 2
        assert records[0]["id"] == "301"

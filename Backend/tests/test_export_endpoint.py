import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock

from app.main import app
from app.routes.export_routes import get_extraction_service
from app.services.arrt_api_service import (
    ArrtApiService,
    CaptchaOrAuthError,
    TransientApiError,
)
from app.services.csv_service import CsvService
from app.services.extraction_service import ExtractionService


@pytest.mark.asyncio
async def test_swagger_docs_accessible():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/docs")
        assert res.status_code == 200
        assert "swagger" in res.text.lower() or "html" in res.text.lower()


@pytest.mark.asyncio
async def test_export_endpoint_success_and_deduplication(tmp_path: Path):
    from app.config import Settings
    test_settings = Settings()
    test_settings.exports_dir = tmp_path

    # Mock API service returning ARRT technologist data with deliberate duplicate
    mock_api = AsyncMock(spec=ArrtApiService)

    async def mock_fetch(first_name_pattern, last_name_pattern="%%", client=None):
        if first_name_pattern == "Aa%":
            return [
                {
                    "name": "Aadil A Esmail",
                    "city": "Spring City",
                    "state": "PA",
                    "credential_string": "R.T.(R)(ARRT)",
                    "detail_token": "token_aadil_1",
                },
                {
                    "name": "Aaron B Miller",
                    "city": "Philadelphia",
                    "state": "PA",
                    "credential_string": "R.T.(R)(CT)(ARRT)",
                    "detail_token": "token_aaron_2",
                },
            ]
        elif first_name_pattern == "Ab%":
            return [
                # Duplicate record with identical detail_token
                {
                    "name": "Aadil A Esmail",
                    "city": "Spring City",
                    "state": "PA",
                    "credential_string": "R.T.(R)(ARRT)",
                    "detail_token": "token_aadil_1",
                },
                {
                    "name": "Abby Wilson",
                    "city": "Pittsburgh",
                    "state": "PA",
                    "credential_string": "R.T.(R)(ARRT)",
                    "detail_token": "token_abby_3",
                },
            ]
        return []

    mock_api.fetch_users_by_pattern.side_effect = mock_fetch

    test_csv = CsvService(settings=test_settings)
    test_extraction = ExtractionService(
        settings=test_settings,
        api_service=mock_api,
        csv_service=test_csv,
    )

    app.dependency_overrides[get_extraction_service] = lambda: test_extraction

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "concurrency": 2,
                "output_filename": "test_output.csv",
                "custom_patterns": ["Aa%", "Ab%"],
                "overwrite": True,
            }
            response = await ac.post("/api/users/export-csv", json=payload)
            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert "User extraction completed" in data["message"]
            summary = data["summary"]
            assert summary["total_patterns"] == 2
            assert summary["successful_requests"] == 2
            assert summary["failed_requests"] == 0
            assert summary["total_records_fetched"] == 4
            assert summary["unique_records"] == 3
            assert summary["duplicate_records"] == 1
            assert data["csv_file"] is not None
            assert Path(data["csv_file"]).exists()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_endpoint_partial_failure(tmp_path: Path):
    from app.config import Settings
    test_settings = Settings()
    test_settings.exports_dir = tmp_path

    mock_api = AsyncMock(spec=ArrtApiService)

    async def mock_fetch(first_name_pattern, last_name_pattern="%%", client=None):
        if first_name_pattern == "Aa%":
            return [
                {
                    "name": "Aadil A Esmail",
                    "city": "Spring City",
                    "state": "PA",
                    "credential_string": "R.T.(R)(ARRT)",
                    "detail_token": "token_1",
                }
            ]
        elif first_name_pattern == "Ab%":
            raise TransientApiError("External API timeout after 60s")
        return []

    mock_api.fetch_users_by_pattern.side_effect = mock_fetch

    test_csv = CsvService(settings=test_settings)
    test_extraction = ExtractionService(
        settings=test_settings,
        api_service=mock_api,
        csv_service=test_csv,
    )

    app.dependency_overrides[get_extraction_service] = lambda: test_extraction

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "concurrency": 1,
                "output_filename": "partial.csv",
                "custom_patterns": ["Aa%", "Ab%"],
            }
            response = await ac.post("/api/users/export-csv", json=payload)
            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert "partially" in data["message"]
            summary = data["summary"]
            assert summary["successful_requests"] == 1
            assert summary["failed_requests"] == 1
            assert len(data["failed_patterns"]) == 1
            assert data["failed_patterns"][0]["pattern"] == "Ab%"
            assert "timeout" in data["failed_patterns"][0]["error"].lower()
            assert Path(data["csv_file"]).exists()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_endpoint_captcha_error(tmp_path: Path):
    from app.config import Settings
    test_settings = Settings()
    test_settings.exports_dir = tmp_path

    mock_api = AsyncMock(spec=ArrtApiService)
    mock_api.fetch_users_by_pattern.side_effect = CaptchaOrAuthError("CAPTCHA token expired or invalid")

    test_csv = CsvService(settings=test_settings)
    test_extraction = ExtractionService(
        settings=test_settings,
        api_service=mock_api,
        csv_service=test_csv,
    )

    app.dependency_overrides[get_extraction_service] = lambda: test_extraction

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "concurrency": 1,
                "output_filename": "captcha_fail.csv",
                "custom_patterns": ["Aa%", "Ab%"],
            }
            response = await ac.post("/api/users/export-csv", json=payload)
            assert response.status_code == 200
            data = response.json()

            assert data["success"] is False
            assert "Extraction failed" in data["message"]
            assert data["summary"]["successful_requests"] == 0
            assert len(data["failed_patterns"]) > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_endpoint_request_validation():
    from app.schemas.export_schema import ExportResponse, ExtractionSummary

    dummy_service = AsyncMock(spec=ExtractionService)
    dummy_service.execute_extraction.return_value = ExportResponse(
        success=True,
        message="Validated",
        summary=ExtractionSummary(
            total_patterns=1,
            successful_requests=1,
            failed_requests=0,
            total_records_fetched=0,
            unique_records=0,
            duplicate_records=0,
            duration_seconds=0.01,
        ),
        csv_file="exports/validated.csv",
    )
    app.dependency_overrides[get_extraction_service] = lambda: dummy_service

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            # Concurrency > 5 rejected
            res = await ac.post("/api/users/export-csv", json={"concurrency": 10})
            assert res.status_code == 422

            # Path traversal in output_filename rejected
            res2 = await ac.post("/api/users/export-csv", json={"output_filename": "../etc/passwd"})
            assert res2.status_code == 422

            # Invalid non-alpha prefix rejected
            res3 = await ac.post("/api/users/export-csv", json={"prefix": "123"})
            assert res3.status_code == 422

            # Valid prefix 'ALL' accepted by validation
            res4 = await ac.post("/api/users/export-csv", json={"prefix": "ALL", "custom_patterns": ["Aa%"]})
            assert res4.status_code == 200
    finally:
        app.dependency_overrides.clear()

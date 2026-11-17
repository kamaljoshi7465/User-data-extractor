import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock

from app.main import app
from app.routes.export_routes import get_extraction_service
from app.services.arrt_api_service import ArrtApiService
from app.services.csv_service import CsvService
from app.services.extraction_service import ExtractionService


@pytest.mark.asyncio
async def test_end_to_end_real_csv_export():
    """
    Simulates end-to-end execution of the export endpoint producing a real CSV in exports/.
    """
    mock_api = AsyncMock(spec=ArrtApiService)

    async def mock_fetch(first_name_pattern, last_name_pattern="%%", client=None):
        char = first_name_pattern[1]  # 'a', 'b', etc.
        return [
            {
                "id": f"arrt-{char}-01",
                "firstName": f"A{char}ron",
                "lastName": "Miller",
                "discipline": "Radiography",
                "status": "Certified",
            },
            {
                "id": f"arrt-{char}-02",
                "firstName": f"A{char}manda",
                "lastName": "Smith",
                "discipline": "Radiation Therapy",
                "status": "Active",
            },
        ]

    mock_api.fetch_users_by_pattern.side_effect = mock_fetch

    test_extraction = ExtractionService(
        api_service=mock_api,
    )

    app.dependency_overrides[get_extraction_service] = lambda: test_extraction

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/users/export-csv",
                json={
                    "concurrency": 2,
                    "output_filename": "e2e_verification.csv",
                    "prefix": "A",
                    "overwrite": True,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["summary"]["total_patterns"] == 26
            assert data["summary"]["successful_requests"] == 26
            assert data["summary"]["total_records_fetched"] == 52
            assert data["summary"]["unique_records"] == 52
            assert data["summary"]["duplicate_records"] == 0

            csv_file = Path(data["csv_file"])
            assert csv_file.exists()
            assert csv_file.stat().st_size > 0

            # Clean up the test verification file
            csv_file.unlink(missing_ok=True)
    finally:
        app.dependency_overrides.clear()


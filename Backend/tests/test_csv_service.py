import csv
import pytest
from pathlib import Path
from app.config import Settings
from app.services.csv_service import CsvService


@pytest.mark.asyncio
async def test_csv_incremental_streaming(tmp_path: Path):
    settings = Settings()
    settings.exports_dir = tmp_path
    csv_service = CsvService(settings=settings)

    # 1. Initialize CSV file
    filepath = await csv_service.initialize_csv(output_filename="stream.csv", overwrite=True)
    assert filepath.exists()

    # 2. Append first pattern records
    batch1 = [
        {
            "name": "Aadil A Esmail",
            "city": "Spring City",
            "state": "PA",
            "credential_string": "R.T.(R)(ARRT)",
            "detail_token": "token_1",
        }
    ]
    appended1 = await csv_service.append_records(filepath, batch1)
    assert appended1 == 1

    # 3. Append second pattern records
    batch2 = [
        {
            "name": "Aaron B Miller",
            "city": "Philadelphia",
            "state": "PA",
            "credential_string": "R.T.(R)(CT)(ARRT)",
            "detail_token": "token_2",
        }
    ]
    appended2 = await csv_service.append_records(filepath, batch2)
    assert appended2 == 1

    # 4. Verify CSV content and row count
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Aadil A Esmail"
        assert rows[0]["detail_token"] == "token_1"
        assert rows[1]["name"] == "Aaron B Miller"
        assert rows[1]["detail_token"] == "token_2"


@pytest.mark.asyncio
async def test_csv_generation(tmp_path: Path):
    settings = Settings()
    settings.exports_dir = tmp_path
    csv_service = CsvService(settings=settings)

    records = [
        {"id": "1001", "name": "Kamal Joshi", "state": "TX"},
        {"id": "1002", "name": "Rahul", "state": "CA"},
    ]

    saved_path = await csv_service.write_records_to_csv(
        records=records,
        output_filename="test_users.csv",
        overwrite=True,
    )

    assert saved_path.exists()
    assert saved_path.name == "test_users.csv"

    # Verify BOM and content
    raw_bytes = saved_path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM

    with open(saved_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["id"] == "1001"
        assert rows[0]["name"] == "Kamal Joshi"


@pytest.mark.asyncio
async def test_csv_dynamic_columns_and_ordering(tmp_path: Path):
    settings = Settings()
    settings.exports_dir = tmp_path
    csv_service = CsvService(settings=settings)

    records = [
        {"name": "Aadil Esmail", "city": "Spring City", "state": "PA", "extra_x": "1"},
        {"name": "Aaron Miller", "city": "Philadelphia", "extra_y": "2"},
    ]

    saved_path = await csv_service.write_records_to_csv(
        records=records,
        output_filename="dynamic.csv",
        overwrite=True,
    )

    with open(saved_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        assert "name" in fields
        assert fields.index("name") == 0
        assert "city" in fields
        assert "state" in fields
        assert "extra_x" in fields
        assert "extra_y" in fields


@pytest.mark.asyncio
async def test_csv_collision_handling(tmp_path: Path):
    settings = Settings()
    settings.exports_dir = tmp_path
    csv_service = CsvService(settings=settings)

    records = [{"name": "Test User"}]

    path1 = await csv_service.write_records_to_csv(records, output_filename="dup.csv", overwrite=False)
    path2 = await csv_service.write_records_to_csv(records, output_filename="dup.csv", overwrite=False)

    assert path1.exists()
    assert path2.exists()
    assert path1 != path2
    assert "dup_" in path2.stem

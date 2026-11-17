import asyncio
import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config import Settings, get_settings

logger = logging.getLogger("arrt_extractor.csv")

# Standard ARRT Table columns matching the external directory output
DEFAULT_ARRT_COLUMNS = [
    "name",
    "city",
    "state",
    "credential_string",
    "detail_token",
]

# Preferred leading columns for consistent user profile view
PREFERRED_COLUMN_ORDER = [
    "name",
    "city",
    "state",
    "credential_string",
    "detail_token",
    "id",
    "userid",
    "user_id",
    "arrtid",
    "arrt_id",
    "idnumber",
    "credentialnumber",
    "verificationid",
    "registrationnumber",
    "firstname",
    "first_name",
    "lastname",
    "last_name",
    "middlename",
    "middle_name",
    "fullname",
    "full_name",
    "zip",
    "postalcode",
    "postal_code",
    "status",
    "discipline",
    "credentials",
]


class CsvService:
    """
    Thread-safe and asynchronous-safe CSV generator that writes flattened user records
    with streaming/incremental appending, dynamic column detection, and Excel-friendly UTF-8 BOM encoding.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._write_lock = asyncio.Lock()

    def get_target_filepath(self, filename: str, overwrite: bool = False) -> Path:
        """
        Determines the safe destination filepath within exports/ directory.
        Avoids unintentional overwrites by generating a unique timestamped name if necessary.
        """
        clean_name = Path(filename).name
        if not clean_name.lower().endswith(".csv"):
            clean_name = f"{clean_name}.csv"

        dest_dir = self.settings.exports_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        target = dest_dir / clean_name
        if target.exists() and not overwrite:
            stem = target.stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = dest_dir / f"{stem}_{timestamp}.csv"

        return target

    def _determine_columns(self, records: List[Dict[str, Any]]) -> List[str]:
        """
        Gathers all unique keys across records and orders them logically.
        Primary identifier and name columns are placed first, followed by remaining
        columns sorted alphabetically.
        """
        all_keys: Set[str] = set(DEFAULT_ARRT_COLUMNS)
        for record in records:
            all_keys.update(record.keys())

        sorted_keys = sorted(all_keys)
        pref_lookup = {col.lower(): idx for idx, col in enumerate(PREFERRED_COLUMN_ORDER)}

        def sort_priority(key: str) -> tuple:
            normalized = key.lower().replace("_", "").replace("-", "")
            return (pref_lookup.get(normalized, 999), key)

        return sorted(sorted_keys, key=sort_priority)

    async def initialize_csv(
        self,
        output_filename: str = "users_export.csv",
        overwrite: bool = False,
        columns: Optional[List[str]] = None,
    ) -> Path:
        """
        Initializes a CSV file in exports/ with UTF-8 BOM and headers.
        Called at the start of extraction so records can be appended incrementally in real-time.
        """
        async with self._write_lock:
            target_path = self.get_target_filepath(output_filename, overwrite=overwrite)
            cols = columns or DEFAULT_ARRT_COLUMNS

            def _sync_init():
                with open(target_path, mode="w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                    writer.writeheader()

            await asyncio.to_thread(_sync_init)
            logger.info(f"Initialized CSV file ready for incremental streaming: {target_path}")
            return target_path

    async def append_records(
        self,
        filepath: Path,
        records: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
    ) -> int:
        """
        Appends a batch of newly fetched user records to the CSV file immediately.
        Ensures thread-safe file access via asyncio.Lock.
        """
        if not records:
            return 0

        async with self._write_lock:
            cols = columns or self._determine_columns(records)

            def _sync_append():
                # If file doesn't exist or is empty, write header first
                write_header = (not filepath.exists()) or (filepath.stat().st_size == 0)

                with open(filepath, mode="a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=cols,
                        extrasaction="ignore",
                        quoting=csv.QUOTE_MINIMAL,
                    )
                    if write_header:
                        writer.writeheader()

                    for rec in records:
                        row = {}
                        for col in cols:
                            val = rec.get(col, "")
                            if val is None:
                                row[col] = ""
                            elif isinstance(val, (dict, list)):
                                row[col] = json.dumps(val, ensure_ascii=False) if isinstance(val, list) else str(val)
                            else:
                                row[col] = str(val)
                        writer.writerow(row)
                    f.flush()

            await asyncio.to_thread(_sync_append)
            logger.info(f"Appended {len(records)} records to {filepath.name}")
            return len(records)

    async def write_records_to_csv(
        self,
        records: List[Dict[str, Any]],
        output_filename: str = "users_export.csv",
        overwrite: bool = False,
    ) -> Path:
        """
        Writes complete list of records to CSV in a single batch (atomic write via temp file).
        """
        async with self._write_lock:
            target_path = self.get_target_filepath(output_filename, overwrite=overwrite)
            tmp_path = target_path.with_suffix(".tmp")

            try:
                await asyncio.to_thread(self._sync_write, records, target_path, tmp_path)
                logger.info(f"Successfully generated CSV with {len(records)} records at: {target_path}")
                return target_path
            except Exception as exc:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                logger.error(f"Failed writing CSV to {target_path}: {exc}")
                raise

    def _sync_write(
        self,
        records: List[Dict[str, Any]],
        target_path: Path,
        tmp_path: Path,
    ) -> None:
        """Synchronous file writing logic executed in a background thread."""
        columns = self._determine_columns(records)

        with open(tmp_path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=columns,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()

            for rec in records:
                row = {}
                for col in columns:
                    val = rec.get(col, "")
                    if val is None:
                        row[col] = ""
                    elif isinstance(val, (dict, list)):
                        row[col] = json.dumps(val, ensure_ascii=False) if isinstance(val, list) else str(val)
                    else:
                        row[col] = str(val)
                writer.writerow(row)

        os.replace(tmp_path, target_path)

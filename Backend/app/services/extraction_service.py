import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from app.config import Settings, get_settings
from app.schemas.export_schema import (
    ExportRequest,
    ExportResponse,
    ExtractionSummary,
    PatternFailure,
)
from app.services.arrt_api_service import (
    ArrtApiException,
    ArrtApiService,
    CaptchaOrAuthError,
    ServerOverloadedError,
)
from app.services.csv_service import CsvService
from app.utils.pattern_generator import generate_first_name_patterns

logger = logging.getLogger("arrt_extractor.extraction")

# Known identifier keys to look for when deduplicating user records
CANDIDATE_ID_KEYS = [
    "detail_token",
    "detailtoken",
    "token",
    "id",
    "userid",
    "user_id",
    "arrtid",
    "arrt_id",
    "idnumber",
    "credentialnumber",
    "verificationid",
    "registrationnumber",
]


class ExtractionService:
    """
    Orchestrates the entire user extraction process:
    - Pattern generation (Aa%..Zz% across all alphabet combinations)
    - Bounded concurrency with asyncio.Semaphore
    - Real-time incremental streaming write to CSV as each pattern finishes
    - Deduplication against external detail token or composite key
    - Safe error containment & overload protection
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        api_service: Optional[ArrtApiService] = None,
        csv_service: Optional[CsvService] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.api_service = api_service or ArrtApiService(settings=self.settings)
        self.csv_service = csv_service or CsvService(settings=self.settings)

    def extract_record_id(self, record: Dict[str, Any]) -> str:
        """
        Determines the unique identifier for a user record.
        Prioritizes the external ARRT detail_token; falls back to a deterministic SHA256
        hash of the technologist's Name + City + State + Credential.
        """
        lower_map = {k.lower().replace("_", "").replace("-", ""): v for k, v in record.items()}

        for key in CANDIDATE_ID_KEYS:
            normalized_key = key.lower().replace("_", "").replace("-", "")
            if normalized_key in lower_map:
                val = lower_map[normalized_key]
                if val is not None and str(val).strip():
                    return str(val).strip()

        # Fallback: Hash key identifying attributes (Name + City + State + Credential)
        name = str(record.get("name", "")).strip().lower()
        city = str(record.get("city", "")).strip().lower()
        state = str(record.get("state", "")).strip().upper()
        cred = str(record.get("credential_string", "")).strip().lower()
        composite = f"{name}|{city}|{state}|{cred}"

        if name:
            return hashlib.sha256(composite.encode("utf-8")).hexdigest()

        # Final fallback: canonical json
        canonical = json.dumps(record, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def execute_extraction(self, request: ExportRequest) -> ExportResponse:
        """
        Runs the complete extraction workflow:
        Generates patterns, fetches them, deduplicates, and incrementally writes
        each response to CSV in real-time.
        """
        start_time = time.time()
        logger.info(
            f"Extraction started. Concurrency={request.concurrency}, Prefix='{request.prefix}', "
            f"Target file='{request.output_filename}'"
        )

        # 1. Determine search patterns (Aa%..Zz% if 'ALL' or custom)
        if request.custom_patterns:
            patterns = request.custom_patterns
        else:
            patterns = generate_first_name_patterns(prefix=request.prefix)

        total_patterns = len(patterns)
        logger.info(f"Generated {total_patterns} search patterns to process.")

        # 2. Initialize the CSV file upfront so records can be appended immediately
        csv_path = await self.csv_service.initialize_csv(
            output_filename=request.output_filename,
            overwrite=request.overwrite,
        )

        # 3. Concurrency bounds and state tracking
        concurrency_limit = min(request.concurrency, self.settings.max_concurrency)
        semaphore = asyncio.Semaphore(concurrency_limit)
        state_lock = asyncio.Lock()

        successful_requests = 0
        failed_requests = 0
        total_records_fetched = 0
        duplicate_records = 0

        unique_records: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        failed_patterns: List[PatternFailure] = []
        abort_extraction = False
        abort_reason = ""

        # Use an AsyncClient session for connection pooling across pattern requests
        timeout = httpx.Timeout(self.settings.request_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:

            async def process_pattern(pattern: str) -> None:
                nonlocal abort_extraction, abort_reason, successful_requests, failed_requests
                nonlocal total_records_fetched, duplicate_records

                if abort_extraction:
                    async with state_lock:
                        failed_requests += 1
                        failed_patterns.append(
                            PatternFailure(pattern=pattern, error=f"Skipped: Extraction halted due to {abort_reason}")
                        )
                    return

                async with semaphore:
                    if abort_extraction:
                        async with state_lock:
                            failed_requests += 1
                            failed_patterns.append(
                                PatternFailure(pattern=pattern, error=f"Skipped: Extraction halted due to {abort_reason}")
                            )
                        return

                    logger.info(f"Processing search pattern: firstName='{pattern}', lastName='{request.last_name}'")
                    try:
                        records = await self.api_service.fetch_users_by_pattern(
                            first_name_pattern=pattern,
                            last_name_pattern=request.last_name,
                            client=client,
                        )

                        # Process newly retrieved records and write to CSV immediately
                        new_unique_batch: List[Dict[str, Any]] = []
                        async with state_lock:
                            successful_requests += 1
                            total_records_fetched += len(records)

                            for rec in records:
                                rec_id = self.extract_record_id(rec)
                                if rec_id in seen_ids:
                                    duplicate_records += 1
                                else:
                                    seen_ids.add(rec_id)
                                    unique_records.append(rec)
                                    new_unique_batch.append(rec)

                        # Immediately stream new unique records to CSV
                        if new_unique_batch:
                            await self.csv_service.append_records(csv_path, new_unique_batch)
                            logger.info(
                                f"Pattern '{pattern}' saved {len(new_unique_batch)} new unique records to CSV. "
                                f"Total unique records saved so far: {len(seen_ids)}"
                            )
                        else:
                            logger.info(f"Pattern '{pattern}' returned {len(records)} records (0 new unique).")

                    except ServerOverloadedError as exc:
                        async with state_lock:
                            abort_extraction = True
                            abort_reason = "external server overload (HTTP 429/503)"
                            failed_requests += 1
                            failed_patterns.append(PatternFailure(pattern=pattern, error=str(exc)))
                        logger.critical(f"Aborting further requests to protect external server: {exc}")

                    except CaptchaOrAuthError as exc:
                        async with state_lock:
                            abort_extraction = True
                            abort_reason = "invalid or expired CAPTCHA / session token"
                            failed_requests += 1
                            failed_patterns.append(PatternFailure(pattern=pattern, error=str(exc)))
                        logger.critical(f"Aborting extraction due to authentication/CAPTCHA failure: {exc}")

                    except ArrtApiException as exc:
                        async with state_lock:
                            failed_requests += 1
                            failed_patterns.append(PatternFailure(pattern=pattern, error=str(exc)))
                        logger.error(f"Pattern '{pattern}' failed: {exc}")

                    except Exception as exc:
                        async with state_lock:
                            failed_requests += 1
                            failed_patterns.append(PatternFailure(pattern=pattern, error=f"Unexpected error: {str(exc)}"))
                        logger.error(f"Unexpected error processing pattern '{pattern}': {exc}", exc_info=True)

            # Process all patterns
            tasks = [process_pattern(p) for p in patterns]
            await asyncio.gather(*tasks)

        duration = round(time.time() - start_time, 2)
        unique_count = len(unique_records)

        logger.info(
            f"Extraction finished in {duration}s. Fetched: {total_records_fetched}, "
            f"Unique: {unique_count}, Duplicates skipped: {duplicate_records}, "
            f"Successful patterns: {successful_requests}/{total_patterns}"
        )

        csv_file_path: Optional[str] = str(csv_path)

        # If every request failed and 0 records were retrieved, clean up empty CSV
        if successful_requests == 0 and total_records_fetched == 0:
            if csv_path.exists() and csv_path.stat().st_size <= 100:
                csv_path.unlink(missing_ok=True)
            csv_file_path = None

        # Determine overall success status
        is_success = successful_requests > 0 and (unique_count > 0 or total_records_fetched == 0)

        if successful_requests == 0:
            status_message = "Extraction failed: All pattern requests encountered errors."
            if abort_reason:
                status_message += f" Extraction was aborted due to {abort_reason}."
        elif failed_requests > 0:
            status_message = (
                f"User extraction partially completed with {successful_requests}/{total_patterns} successful patterns. "
                f"Generated CSV with {unique_count} unique records."
            )
        else:
            status_message = (
                f"User extraction completed successfully. "
                f"Retrieved {unique_count} unique records across {total_patterns} patterns."
            )

        return ExportResponse(
            success=is_success,
            message=status_message,
            summary=ExtractionSummary(
                total_patterns=total_patterns,
                successful_requests=successful_requests,
                failed_requests=failed_requests,
                total_records_fetched=total_records_fetched,
                unique_records=unique_count,
                duplicate_records=duplicate_records,
                duration_seconds=duration,
            ),
            csv_file=csv_file_path,
            failed_patterns=failed_patterns,
        )

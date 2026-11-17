import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.export_schema import ExportRequest, ExportResponse
from app.services.extraction_service import ExtractionService

logger = logging.getLogger("arrt_extractor.routes")

router = APIRouter(prefix="/api/users", tags=["User Extraction"])


def get_extraction_service() -> ExtractionService:
    """Dependency provider for ExtractionService."""
    return ExtractionService()


@router.post(
    "/export-csv",
    response_model=ExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract ARRT users and export to CSV",
    description=(
        "Executes partitioned asynchronous searches against the external ARRT directory "
        "using alphabetical first-name patterns with bounded concurrency, deduplicates records, "
        "and saves the results into an Excel-compatible CSV file."
    ),
)
async def export_users_csv(
    request: ExportRequest,
    service: ExtractionService = Depends(get_extraction_service),
) -> ExportResponse:
    """
    Main extraction endpoint:
    - Generates search patterns ('Aa%' .. 'Az%')
    - Sends controlled asynchronous requests
    - Extracts & flattens user records
    - Deduplicates using unique external IDs
    - Writes records to CSV in exports/ directory
    - Returns comprehensive summary statistics
    """
    try:
        response = await service.execute_extraction(request)
        return response
    except Exception as exc:
        logger.error(f"Fatal error during user extraction: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server error occurred during extraction: {str(exc)}",
        ) from exc


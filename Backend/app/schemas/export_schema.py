import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ExportRequest(BaseModel):
    """Extraction request payload."""

    concurrency: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of concurrent asynchronous requests (conservative max of 5)."
    )
    output_filename: str = Field(
        default="users_export.csv",
        description="Target CSV file name inside exports/ directory."
    )
    prefix: str = Field(
        default="ALL",
        min_length=1,
        max_length=5,
        description="First-name prefix: 'ALL' produces Aa%..Zz% (676 patterns across all letters). Single letter e.g. 'A' produces Aa%..Az%."
    )
    custom_patterns: Optional[List[str]] = Field(
        default=None,
        description="Optional explicit list of first-name patterns overriding prefix generation."
    )
    last_name: str = Field(
        default="%%",
        description="Last-name search pattern (default '%%')."
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite an existing CSV file of the same name or append a unique suffix."
    )

    @field_validator("output_filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("output_filename cannot be empty.")
        if not value.lower().endswith(".csv"):
            value = f"{value}.csv"
        # Prevent directory traversal attacks
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError("output_filename must be a simple file name without path separators.")
        # Ensure only safe filename characters
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", value):
            raise ValueError("output_filename contains invalid characters. Use letters, numbers, underscores, and dashes.")
        return value

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        value = value.strip()
        if value.upper() in ("ALL", "A-Z", "*"):
            return "ALL"
        if not value.isalpha():
            raise ValueError("Prefix must contain only alphabetic characters (e.g. 'ALL', 'A', 'B', 'Sm').")
        return value.capitalize()


class PatternFailure(BaseModel):
    """Information on an individual pattern request that failed."""

    pattern: str = Field(..., description="The search pattern that failed.")
    error: str = Field(..., description="Human-readable explanation of failure reason.")


class ExtractionSummary(BaseModel):
    """Aggregate statistics for the extraction run."""

    total_patterns: int = Field(..., description="Total number of patterns processed.")
    successful_requests: int = Field(..., description="Count of successfully executed pattern searches.")
    failed_requests: int = Field(..., description="Count of pattern searches that encountered errors.")
    total_records_fetched: int = Field(..., description="Raw count of records returned across all queries.")
    unique_records: int = Field(..., description="Count of unique records after deduplication.")
    duplicate_records: int = Field(..., description="Count of duplicate records identified and filtered out.")
    duration_seconds: float = Field(..., description="Total wall-clock duration of extraction in seconds.")


class ExportResponse(BaseModel):
    """Response returned upon completion of CSV extraction."""

    success: bool = Field(..., description="True if at least one pattern succeeded and CSV was produced.")
    message: str = Field(..., description="Summary status message.")
    summary: ExtractionSummary = Field(..., description="Extraction statistics.")
    csv_file: Optional[str] = Field(None, description="Path to the generated CSV file.")
    failed_patterns: List[PatternFailure] = Field(
        default_factory=list,
        description="List of patterns that failed along with error details."
    )


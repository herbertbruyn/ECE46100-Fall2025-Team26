from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, Optional


class MetricType(Enum):
    """Enumeration of supported metric types (names mirror NDJSON keys)."""
    SIZE_SCORE = "size_score"
    LICENSE = "license"
    RAMP_UP_TIME = "ramp_up_time"
    BUS_FACTOR = "bus_factor"
    DATASET_AND_CODE_SCORE = "dataset_and_code_score"
    DATASET_QUALITY = "dataset_quality"
    CODE_QUALITY = "code_quality"
    PERFORMANCE_CLAIMS = "performance_claims"
    REPRODUCIBILITY = "reproducibility"


@dataclass(frozen=True)
class MetricResult:
    """
    Result of a metric calculation.

    Attributes:
        metric_type: Type of metric calculated
        value: float (0..1) OR SizeScore mapping, depending on metric
        details: Additional details about the calculation
        latency_ms: Time to calculate metric, integer milliseconds (rounded)
        error: Error message if calculation failed (None if success)
    """
    metric_type: MetricType
    value: float
    details: Dict[str, Any]
    latency_ms: int
    error: Optional[str] = None

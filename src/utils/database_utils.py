"""Database utilities - backward compatibility shim.

This file maintains backward compatibility by importing from the new modular structure.
All functionality has been moved to src/utils/database/ directory.
"""

from .database import (
    DatabaseUtils,
    AllocationUtils,
    SegmentCRUD,
    SegmentQueries,
    StatisticsUtils,
)

__all__ = [
    "DatabaseUtils",
    "AllocationUtils",
    "SegmentCRUD",
    "SegmentQueries",
    "StatisticsUtils",
]

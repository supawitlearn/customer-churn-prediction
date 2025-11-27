"""
Module for generating reservation behavioral features.
"""
from typing import Dict, List

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DATE_TYPES = ["holiday", "weekend", "weekday"]
TIME_PERIODS = {
    "early_morning": (0, 6),
    "morning_peak": (6, 10),
    "daytime": (10, 16),
    "evening_peak": (16, 20),
    "late_night": (20, 24),
}

# Column selections
DISTANCE_IMPUTATION_COLS = ["txn_id", "trip_hour", "distance"]
PREDICTORS = ["trip_hour"]
TARGET = "distance"

# Customer reservation behavior features
STATE_GROUPS: Dict[str, List[str]] = {
    "overall": ["COMPLETE", "FINISH", "RESERVE", "DRIVE", "CANCEL", "REJECT"],
    "completed": ["COMPLETE", "FINISH", "RESERVE", "DRIVE"],
    "cancelled": ["CANCEL"],
    "rejected": ["REJECT"],
}
STATE_KEYS: List[str] = ["overall", "completed", "cancelled", "rejected"]
CAPPED_MAX = 90
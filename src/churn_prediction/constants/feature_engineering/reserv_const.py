"""
Module for generating reservation behavioral features.
"""

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
DISTANCE_IMPUTATION_COLS = ["txn_id", "duration_hour", "distance"]
PREDICTORS = ["duration_hour"]
TARGET = "distance"
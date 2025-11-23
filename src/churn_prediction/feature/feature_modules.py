from src.churn_prediction.feature.station_location_profile_feat import StationLocationProfileFeatures
from src.churn_prediction.feature.reservation_behavioral_feat import ReservationBehavioralFeatures
from src.churn_prediction.feature.app_behavior_feat import AppBehaviorFeatures
from src.churn_prediction.feature.customer_app_behavior_feat import CustomerAppBehaviorFeatures

def feature_modules(
) -> dict:
    """
    Returns a dictionary of feature engineering classes.

    Returns:
        dict: A dictionary with feature engineering class references.
    """
    return {
        "StationLocationProfileFeatures": StationLocationProfileFeatures,
        "ReservationBehavioralFeatures": ReservationBehavioralFeatures,
        "AppBehaviorFeatures": AppBehaviorFeatures,
        "CustomerAppBehaviorFeatures": CustomerAppBehaviorFeatures,
    }
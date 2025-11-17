BUFFER_RADIUS: int = 1000

# Group 1: Daily Life & Necessity
poi_group_1_daily_life: dict = {
    "amenity": ["school", "university", "library", "clinic", "hospital", "post_office", "fuel", "charging_station", "parking"],
    "office": ["company", "government"],
    "healthcare": ["hospital", "clinic", "pharmacy"],
}

# Group 2: Shopping & Personal Errands
poi_group_2_shopping: dict = {
    "shop": [
        "mall", "supermarket", "convenience", "department_store",
        "bakery", "electronics", "beauty", "hairdresser"
    ],
    "amenity_shopping": ["bank", "atm", "post_office", "car_wash", "vending_machine"],
}

# Group 3: Leisure, Social & Lifestyle
poi_group_3_leisure: dict = {
    "amenity_leisure": ["restaurant", "cafe", "bar", "pub", "nightclub", "cinema"],
    "leisure": ["park", "stadium", "sports_centre", "swimming_pool", "golf_course"],
    "tourism_leisure": ["attraction", "museum", "gallery", "theme_park"],
}

# Group 4: Travel, Religious & Tourism
poi_group_4_travel_tourism: dict = {
    "aeroway": ["aerodrome"],
    "railway": ["station", "subway_entrance"],
    "public_transport": ["station", "bus_station", "stop_position"],
    "tourism_travel": ["hotel", "resort", "hostel", "guest_house"],
    "religion": ["temple", "church", "mosque"],
    "historic": ["monument", "castle"]
}
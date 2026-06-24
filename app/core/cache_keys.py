# TTL constraints(in sec)
CACHE_TTL_RESTAURANT_DETAIL = 60
CACHE_TTL_REVIEWS = 300
CACHE_TTL_CUISINE_LIST = 3600
CACHE_TTL_DISH_SEARCH = 60
CACHE_TTL_DISCOVERY_FEED = 30


def restaurant_detail_key(restaurant_id) -> str:
    return f"restaurant:detail:{restaurant_id}"


def restaurant_reviews_key(restaurant_id, skip: int, limit: int) -> str:
    return f"restaurant:reviews:{restaurant_id}:{skip}:{limit}"


def cuisine_list_key() -> str:
    return "cuisines:active:list"


def dish_search_key(
    query: str, lat: float, lon: float, radius_km: float, cursor: str | None
) -> str:

    lat_r, lon_r = round(lat, 3), round(lon, 3)
    cursor_part = cursor or "first"
    return (
        f"dish:search:{query.lower().strip()}:{lat_r}:{lon_r}:{radius_km}:{cursor_part}"
    )


def discovery_feed_key(
    lat, lon, city, cuisine_id, cursor: str | None, limit: int
) -> str:
    lat_part = round(lat, 3) if lat is not None else "none"
    lon_part = round(lon, 3) if lon is not None else "none"
    city_part = city.lower().strip() if city else "none"
    cuisine_part = str(cuisine_id) if cuisine_id else "none"
    cursor_part = cursor or "first"
    return f"discover:{lat_part}:{lon_part}:{city_part}:{cuisine_part}:{cursor_part}:{limit}"


def discovery_feed_pattern_for_restaurant_city(city: str) -> str:

    return f"discover:*:{city.lower().strip()}:*"

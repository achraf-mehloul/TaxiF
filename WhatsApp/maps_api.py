import googlemaps
from datetime import datetime
from config import GOOGLE_MAPS_API_KEY

gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def geocode_address(address):
    res = gmaps.geocode(address)
    if not res:
        return None
    loc = res[0]['geometry']['location']
    return {'lat': loc['lat'], 'lng': loc['lng'], 'formatted_address': res[0].get('formatted_address')}

def get_route_info(origin_latlng, dest_latlng):
    now = datetime.now()
    directions = gmaps.directions(origin_latlng, dest_latlng, mode="driving", departure_time=now)
    if not directions:
        return None
    leg = directions[0]['legs'][0]
    return {
        'distance_meters': leg['distance']['value'],
        'duration_seconds': leg['duration']['value'],
        'distance_text': leg['distance']['text'],
        'duration_text': leg['duration']['text'],
    }

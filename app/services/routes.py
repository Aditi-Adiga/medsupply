"""Saved road-route estimates. No live traffic or invented fallback distances."""
import csv
import math
from functools import lru_cache
from pathlib import Path

ROUTE_FILE = Path(__file__).resolve().parents[2] / 'hospital_routes.csv'


@lru_cache(maxsize=1)
def load_routes():
    result = {}
    with ROUTE_FILE.open(newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            key = (row['from_hospital_id'], row['to_hospital_id'])
            if key in result:
                raise ValueError('Duplicate hospital route: ' + str(key))
            if row['route_status'] != 'available':
                continue
            distance = float(row['road_distance_km'])
            travel = int(row['estimated_travel_minutes'])
            preparation = int(row['preparation_minutes'])
            receiving = int(row['receiving_minutes'])
            delivery = int(row['estimated_delivery_minutes'])
            if (not math.isfinite(distance) or distance <= 0 or travel <= 0
                    or preparation < 0 or receiving < 0 or delivery != travel + preparation + receiving):
                raise ValueError('Invalid hospital route: ' + str(key))
            result[key] = {
                'donor_city': row['from_city'], 'recipient_city': row['to_city'],
                'road_distance_km': distance, 'estimated_delivery_minutes': delivery,
                'estimated_travel_minutes': travel, 'route_source': row['source'],
                'route_calculated_at_utc': row['calculated_at_utc'],
                'preparation_minutes': preparation, 'receiving_minutes': receiving,
            }
    return result


def route_for(donor, recipient):
    return load_routes().get((donor, recipient))

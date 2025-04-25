from flask import Flask, render_template
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
from pathlib import Path
import googlemaps

app = Flask(__name__)

# Berkeley's center coordinates as fallback
BERKELEY_CENTER = {"lat": 37.8719, "lng": -122.2585}

def geocode_address(address):
    """Geocode an address using cached results or return Berkeley center coordinates."""
    cache_file = Path("geocode_cache.json")
    if cache_file.exists():
        with open(cache_file, "r") as f:
            geocode_cache = json.load(f)
    else:
        geocode_cache = {}

    if address in geocode_cache:
        return geocode_cache[address]

    # If no API key is set, return Berkeley center coordinates
    return BERKELEY_CENTER

def fetch_crime_data():
    # Get data for the last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    base_url = "https://services7.arcgis.com/vIHhVXjE1ToSg0Fz/arcgis/rest/services/Berkeley_PD_Cases_2016_to_Current/FeatureServer/0/query"
    where_clause = (
        f"Occurred_Datetime >= DATE '{start_date.strftime('%Y-%m-%d')} 00:00:00' "
        f"AND Occurred_Datetime < DATE '{end_date.strftime('%Y-%m-%d')} 23:59:59'"
    )

    params = {
        "where": where_clause,
        "outFields": "Incident_Type,Statute_Type,Block_Address,Occurred_Datetime,Statute_Description",
        "outSR": "4326",
        "f": "json"
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        
        if not features:
            return []
            
        crimes = []
        for feature in features:
            attributes = feature.get("attributes", {})
            if attributes:
                # Convert timestamp to readable format
                if "Occurred_Datetime" in attributes:
                    timestamp = attributes["Occurred_Datetime"]
                    if timestamp:
                        attributes["Occurred_Datetime"] = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M')
                
                # Add coordinates if address is available
                if "Block_Address" in attributes and attributes["Block_Address"]:
                    coords = geocode_address(attributes["Block_Address"])
                    if coords:
                        attributes["latitude"] = coords["lat"]
                        attributes["longitude"] = coords["lng"]
                
                crimes.append(attributes)
        
        return crimes
    except Exception as e:
        print(f"Error fetching crime data: {str(e)}")
        return []

@app.route('/')
def index():
    crimes = fetch_crime_data()
    return render_template('index.html', crimes=crimes)

@app.route('/crime/<int:crime_id>')
def crime_detail(crime_id):
    crimes = fetch_crime_data()
    if 0 <= crime_id < len(crimes):
        return render_template('crime_detail.html', crime=crimes[crime_id])
    return "Crime not found", 404

if __name__ == '__main__':
    app.run(host='localhost', port=8000, debug=True)

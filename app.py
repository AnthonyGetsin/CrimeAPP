import requests
import time
import folium
import osmnx as ox
import geopandas as gpd
import pandas as pd
import json
from pathlib import Path
from shapely.geometry import Point
from shapely.strtree import STRtree
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from concurrent.futures import ThreadPoolExecutor, as_completed
from folium.plugins import MarkerCluster
from tqdm import tqdm
from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
import os
from werkzeug.serving import run_simple

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ============================================================================
# 1. SETUP CACHING AND CONFIGURATION (Keep your original code)
# ============================================================================
CACHE_FILE = Path("geocode_cache.json")
GEOCODING_RATE_LIMIT = 1
MAX_WORKERS = 5

geolocator = Nominatim(user_agent="berkeley_crime_mapper")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODING_RATE_LIMIT)

if CACHE_FILE.exists():
    with open(CACHE_FILE) as f:
        geocode_cache = json.load(f)
else:
    geocode_cache = {}

def save_cache():
    temp_file = CACHE_FILE.with_suffix(".tmp")
    with open(temp_file, "w") as f:
        json.dump(geocode_cache, f)
    temp_file.replace(CACHE_FILE)

# ============================================================================
# 2. GEOCODING AND DATA FETCHING (Keep your original code)
# ============================================================================
def geocode_address(address):
    if not address:
        return None, None
    
    cache_key = f"{address}, Berkeley, CA"
    if cache_key in geocode_cache:
        return geocode_cache[cache_key]
    
    try:
        location = geocode(cache_key)
        if location:
            coords = (location.latitude, location.longitude)
            geocode_cache[cache_key] = coords
            return coords
    except Exception as e:
        print(f"\nGeocoding failed for {address}: {str(e)}")
    
    geocode_cache[cache_key] = (None, None)
    return None, None

def fetch_crime_data():
    base_url = "https://services7.arcgis.com/vIHhVXjE1ToSg0Fz/arcgis/rest/services/Berkeley_PD_Cases_2016_to_Current/FeatureServer/0/query"
    today  = datetime.utcnow()
    start  = today - pd.Timedelta(days=60)   # last 60 days
    where_clause = (
        f"Occurred_Datetime >= DATE '{start:%Y-%m-%d} 00:00:00' "
        f"AND Occurred_Datetime < DATE '{today:%Y-%m-%d} 00:00:00'")

    params = {
        "where": where_clause,
        "outFields": "*",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": 2000
    }

    for attempt in range(3):
        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return pd.DataFrame([f["attributes"] for f in data.get("features", [])])
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed: {str(e)}")
            time.sleep(2**attempt)
    
    raise Exception("Failed to fetch crime data after 3 attempts")

# ============================================================================
# 3. SPATIAL PROCESSING (Keep your original code)
# ============================================================================
def create_spatial_index():
    street_network_cache = Path("berkeley_streets.gpkg")
    
    if street_network_cache.exists():
        gdf_edges = gpd.read_file(street_network_cache, layer="edges")
    else:
        G = ox.graph_from_place("Berkeley, California, USA", network_type="drive")
        gdf_edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
        gdf_edges.to_file(street_network_cache, layer="edges")
    
    str_tree = STRtree(gdf_edges.geometry)
    geom_to_index = {geom: idx for idx, geom in zip(gdf_edges.index, gdf_edges.geometry)}
    return gdf_edges, str_tree, geom_to_index

# ============================================================================
# 4. API ENDPOINT (New addition)
# ============================================================================
@app.route('/api/crimes')
def api_get_crimes():
    """Endpoint for frontend to get crime data in JSON format"""
    try:
        df = fetch_crime_data()
        df["Occurred_Datetime"] = pd.to_datetime(df["Occurred_Datetime"], unit="ms")
        
        # Process addresses using existing cache
        def _coords(addr):
            key = f"{addr}, Berkeley, CA"
            lat, lon = geocode_cache.get(key, (None, None))
            if lat is None:                       # cache miss → geocode now
                lat, lon = geocode_address(addr)
            return lat, lon

        df["coords"] = df["Block_Address"].apply(_coords)
        save_cache()


        df[["latitude", "longitude"]] = pd.DataFrame(df["coords"].tolist(), index=df.index)
        df = df.dropna(subset=["latitude", "longitude"])
        
        return jsonify({
            "data": df.to_dict("records"),
            "metadata": {
                "count": len(df),
                "last_updated": datetime.now().isoformat()
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# 5. MAIN PROCESSING PIPELINE (Keep your original code)
# ============================================================================
def main():
    print("Fetching crime data...")
    df = fetch_crime_data()
    df["Occurred_Datetime"] = pd.to_datetime(df["Occurred_Datetime"], unit="ms")
    
    print("\nPreprocessing addresses...")
    address_groups = df.groupby("Block_Address", observed=True)
    unique_addresses = list(address_groups.groups.keys())
    
    print(f"Geocoding {len(unique_addresses)} unique addresses...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(geocode_address, addr): addr for addr in unique_addresses}
        for future in tqdm(as_completed(futures), total=len(unique_addresses), desc="Geocoding"):
            future.result()
    
    save_cache()
    
    print("\nEnriching data with coordinates...")
    df["coords"] = df["Block_Address"].apply(
        lambda x: geocode_cache.get(f"{x}, Berkeley, CA", (None, None)))
    df[["latitude", "longitude"]] = pd.DataFrame(df["coords"].tolist(), index=df.index)
    df = df.dropna(subset=["latitude", "longitude"])
    
    print("Creating spatial index...")
    gdf_edges, str_tree, geom_to_index = create_spatial_index()
    def find_nearest_edge(pt, *, str_tree=str_tree, geom_to_index=geom_to_index):
        geom = str_tree.nearest(pt)
        return geom_to_index.get(geom)

    
    print("Processing crime locations...")
    edge_crime_count = {}
    marker_cluster = MarkerCluster(name="Crime Markers")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        points = [Point(row.longitude, row.latitude) for _, row in df.iterrows()]
        results = list(tqdm(executor.map(find_nearest_edge, points), total=len(points), desc="Matching points"))
    
    for edge_idx in filter(None, results):
        edge_crime_count[edge_idx] = edge_crime_count.get(edge_idx, 0) + 1
    
    print("Generating visualization...")
    m = folium.Map(location=[37.87, -122.27], zoom_start=14)
    marker_cluster.add_to(m)
    
    for _, row in df.iterrows():
        folium.Marker(
            location=[row.latitude, row.longitude],
            popup=f"Crime: {row.Incident_Type}<br>Address: {row.Block_Address}",
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(marker_cluster)
    
    for edge_idx, count in edge_crime_count.items():
        edge = gdf_edges.loc[[edge_idx]]
        folium.GeoJson(
            edge.__geo_interface__,
            style_function=lambda x, count=count: {
                'color': 'red' if count > 3 else 'orange' if count > 1 else 'green',
                'weight': 4 + count,
                'opacity': 0.7
            }
        ).add_to(m)
    
    folium.LayerControl().add_to(m)
    m.save("berkeley_crime_optimized.html")
    print("Map saved successfully!")

# ============================================================================
# 6. RUN BOTH SERVERS
# ============================================================================
if __name__ == "__main__":
    main()                                   # builds cache + map once
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)

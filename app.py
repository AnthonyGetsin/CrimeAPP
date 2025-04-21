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
from tqdm import tqdm  # For progress tracking

# ============================================================================
# 1. SETUP CACHING AND CONFIGURATION
# ============================================================================

CACHE_FILE = Path("geocode_cache.json")
GEOCODING_RATE_LIMIT = 1  # Seconds between requests
MAX_WORKERS = 5  # Threads for parallel processing

# Initialize geocoder with persistent cache
geolocator = Nominatim(user_agent="berkeley_crime_mapper")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODING_RATE_LIMIT)

# Load existing cache
if CACHE_FILE.exists():
    with open(CACHE_FILE) as f:
        geocode_cache = json.load(f)
else:
    geocode_cache = {}

def save_cache():
    """Save cache to disk with atomic write"""
    temp_file = CACHE_FILE.with_suffix(".tmp")
    with open(temp_file, "w") as f:
        json.dump(geocode_cache, f)
    temp_file.replace(CACHE_FILE)

# ============================================================================
# 2. OPTIMIZED GEOCODING WITH CACHING AND BATCH PROCESSING
# ============================================================================

def geocode_address(address):
    """Geocode with persistent cache and error handling"""
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
    
    geocode_cache[cache_key] = (None, None)  # Cache failures to prevent retries
    return None, None

# ============================================================================
# 3. DATA ACQUISITION AND PREPROCESSING
# ============================================================================

def fetch_crime_data():
    """Fetch crime data with error handling and retries"""
    base_url = "https://services7.arcgis.com/vIHhVXjE1ToSg0Fz/arcgis/rest/services/Berkeley_PD_Cases_2016_to_Current/FeatureServer/0/query"
    where_clause = (
        "Occurred_Datetime >= DATE '2025-02-08 00:00:00' "
        "AND Occurred_Datetime < DATE '2025-04-08 00:00:00'"
    )

    params = {
        "where": where_clause,
        "outFields": "*",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": 2000  # Max allowed by the service
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
# 4. SPATIAL PROCESSING OPTIMIZATIONS
# ============================================================================

def create_spatial_index():
    """Create street network spatial index with memoization"""
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
# 5. MAIN PROCESSING PIPELINE
# ============================================================================

def main():
    print("Fetching crime data...")
    df = fetch_crime_data()
    df["Occurred_Datetime"] = pd.to_datetime(df["Occurred_Datetime"], unit="ms")
    
    print("\nPreprocessing addresses...")
    # Process unique addresses first to minimize geocoding
    address_groups = df.groupby("Block_Address", observed=True)
    unique_addresses = list(address_groups.groups.keys())
    
    print(f"Geocoding {len(unique_addresses)} unique addresses...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(geocode_address, addr): addr for addr in unique_addresses}
        for future in tqdm(as_completed(futures), total=len(unique_addresses), desc="Geocoding"):
            future.result()  # We just need to wait for completion
    
    # Save cache after batch geocoding
    save_cache()
    
    # Add coordinates to DataFrame using cached results
    print("\nEnriching data with coordinates...")
    df["coords"] = df["Block_Address"].apply(
        lambda x: geocode_cache.get(f"{x}, Berkeley, CA", (None, None)))
    df[["latitude", "longitude"]] = pd.DataFrame(df["coords"].tolist(), index=df.index)
    df = df.dropna(subset=["latitude", "longitude"])
    
    # Spatial processing
    print("Creating spatial index...")
    gdf_edges, str_tree, geom_to_index = create_spatial_index()
    
    print("Processing crime locations...")
    edge_crime_count = {}
    marker_cluster = MarkerCluster(name="Crime Markers")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        points = [Point(row.longitude, row.latitude) for _, row in df.iterrows()]
        results = list(tqdm(executor.map(find_nearest_edge, points), total=len(points), desc="Matching points"))
    
    for edge_idx in filter(None, results):
        edge_crime_count[edge_idx] = edge_crime_count.get(edge_idx, 0) + 1
    
    # Create map
    print("Generating visualization...")
    m = folium.Map(location=[37.87, -122.27], zoom_start=14)
    marker_cluster.add_to(m)
    
    # Add markers
    for _, row in df.iterrows():
        folium.Marker(
            location=[row.latitude, row.longitude],
            popup=f"Crime: {row.Incident_Type}<br>Address: {row.Block_Address}",
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(marker_cluster)
    
    # Add crime density visualization
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

if __name__ == "__main__":
    start_time = time.time()
    main()
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
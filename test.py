import requests
import os
import json
import re
import folium
import osmnx as ox
import geopandas as gpd
import pandas as pd
import numpy as np
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from tqdm import tqdm
from folium.plugins import HeatMap
from collections import defaultdict
from datetime import datetime

# ============================================================================
# 1. GEOCODER CLASS
# ============================================================================
class Geocoder:
    def __init__(self):
        self.cache_file = "geocoding_cache.json"
        self.cache = self._load_cache()
        self.geolocator = Nominatim(
            user_agent="crime-analysis-contact@example.com",
            timeout=15
        )
        self.geocode = RateLimiter(
            self.geolocator.geocode,
            min_delay_seconds=2,
            max_retries=2,
            error_wait_seconds=10
        )
    
    def _load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f)

    def _normalize_address(self, address):
        address = re.sub(r'\s+', ' ', str(address).strip().upper())
        replacements = {
            r'\bST\b': 'St',
            r'\bAVE\b': 'Ave',
            r'\bBLVD\b': 'Blvd',
            r'\bDR\b': 'Dr',
            r'\bRD\b': 'Rd'
        }
        for pattern, replacement in replacements.items():
            address = re.sub(pattern, replacement, address)
        return address

    def get_coords(self, address):
        normalized = self._normalize_address(address)
        if normalized in self.cache:
            return self.cache[normalized]
        
        try:
            location = self.geocode(f"{normalized}, Berkeley, CA")
            if location:
                self.cache[normalized] = (location.latitude, location.longitude)
                return self.cache[normalized]
        except Exception as e:
            print(f"Geocoding failed for {normalized}: {str(e)}")
            self.cache[normalized] = None
        
        return None

# ============================================================================
# 2. DATA FETCHING WITH COLUMN STANDARDIZATION
# ============================================================================
def fetch_crime_data():
    cache_file = "crime_data_cache.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            df = pd.DataFrame(json.load(f))
    else:
        base_url = "https://services7.arcgis.com/vIHhVXjE1ToSg0Fz/arcgis/rest/services/Berkeley_PD_Cases_2016_to_Current/FeatureServer/0/query"
        
        # Critical fix: Explicitly request Occurred_Datetime with exact case
        params = {
            "where": "1=1",
            "outFields": "Occurred_Datetime,Block_Address,Incident_Type",  # Exact API field name
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": 1000
        }

        response = requests.get(base_url, params=params, timeout=15)
        data = response.json()
        features = data.get("features", [])
        df = pd.DataFrame([feature.get("attributes", {}) for feature in features])

        # Verify we got the datetime field
        if 'Occurred_Datetime' not in df.columns:
            raise KeyError("Occurred_Datetime not in API response! Check field names")

        # Convert timestamp immediately after load
        df['Occurred_Datetime'] = pd.to_datetime(df['Occurred_Datetime'], unit='ms')
        
        with open(cache_file, 'w') as f:
            json.dump(df.to_dict(), f)

    # Remove column renaming - use original API field names
    print("DateTime column verified:", df['Occurred_Datetime'].dtype)
    return df

# ============================================================================
# 3. SPATIAL PROCESSING
# ============================================================================
def get_street_network():
    cache_file = "berkeley_streets.graphml"
    if os.path.exists(cache_file):
        return ox.load_graphml(cache_file)
    
    G = ox.graph_from_place("Berkeley, California, USA", network_type='drive')
    ox.save_graphml(G, cache_file)
    return G

def process_spatial_data(df, G):
    crime_points = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.longitude, df.latitude),
        crs="EPSG:4326"
    ).to_crs(G.graph['crs'])

    X = crime_points.geometry.x.values
    Y = crime_points.geometry.y.values
    
    try:
        nearest_edges = ox.distance.nearest_edges(G, X, Y, interpolate=0.1)
    except TypeError:
        nearest_edges = ox.distance.nearest_edges(G, X, Y)

    edge_tuples = [tuple(map(int, edge)) for edge in nearest_edges]
    edge_counts = defaultdict(int)
    for edge in edge_tuples:
        edge_counts[edge] += 1

    return edge_counts

# ============================================================================
# 4. VISUALIZATION COMPONENTS
# ============================================================================
def create_crime_list(df):
    html = f"""
    <div style="
        position: fixed; 
        top: 20px; 
        left: 20px; 
        z-index: 1000; 
        background: white; 
        padding: 10px; 
        border: 2px solid grey; 
        border-radius: 5px; 
        max-width: 600px;
        max-height: 400px; 
        overflow-y: auto;
        font-family: Arial, sans-serif;
    ">
        <h4 style="margin: 0 0 10px 0; color: #333;">Recent Crimes ({len(df)})</h4>
        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
            <thead>
                <tr style="background: #f0f0f0;">
                    <th style="padding: 5px; border-bottom: 1px solid #ddd;">Type</th>
                    <th style="padding: 5px; border-bottom: 1px solid #ddd;">Location</th>
                    <th style="padding: 5px; border-bottom: 1px solid #ddd;">Date/Time</th>
                </tr>
            </thead>
            <tbody>
    """

    # Handle datetime conversion
    if 'occurred_datetime' in df.columns:
        df['occurred_datetime'] = pd.to_datetime(df['occurred_datetime'], errors='coerce')
        df = df.dropna(subset=['occurred_datetime'])
        df_sorted = df.sort_values('occurred_datetime', ascending=False)
        
        for _, row in df_sorted.iterrows():
            time_str = row['occurred_datetime'].strftime('%Y-%m-%d %I:%M %p')
            html += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 5px;">{row.get('incident_type', 'N/A')}</td>
                    <td style="padding: 5px;">{row.get('block_address', 'N/A')}</td>
                    <td style="padding: 5px; white-space: nowrap;">{time_str}</td>
                </tr>
            """
    else:
        for _, row in df.iterrows():
            html += f"""
                <tr style="border-bottom: 1px solid #eee;">
                    <td style="padding: 5px;">{row.get('incident_type', 'N/A')}</td>
                    <td style="padding: 5px;">{row.get('block_address', 'N/A')}</td>
                </tr>
            """

    html += """
            </tbody>
        </table>
    </div>
    """
    return html

def create_incident_summary(df):
    # Find incident type column with fallback
    incident_col = next(
        (col for col in df.columns 
         if col.lower() in ['incident_type', 'crime_type', 'offense_type']),
        'incident_type'
    )
    
    incident_counts = df[incident_col].value_counts().reset_index()
    incident_counts.columns = ['Incident Type', 'Count']
    
    time_html = ""
    if 'occurred_datetime' in df.columns:
        try:
            df['hour'] = pd.to_datetime(df['occurred_datetime']).dt.hour
            time_counts = df['hour'].value_counts().sort_index().reset_index()
            time_counts.columns = ['Hour', 'Count']
            
            time_html = """
            <h4 style="margin: 15px 0 5px 0; color: #333;">Crimes by Hour</h4>
            <table style="width: 100%; margin-bottom: 10px;">
                <tr style="background: #f0f0f0;">
                    <th style="padding: 5px;">Hour</th>
                    <th style="padding: 5px;">Count</th>
                </tr>
                {}
            </table>
            """.format("\n".join([
                f'<tr><td style="padding: 5px;">{row.Hour:02d}:00</td><td style="padding: 5px;">{row.Count}</td></tr>'
                for _, row in time_counts.iterrows()
            ]))
        except Exception as e:
            print(f"Could not process time data: {e}")

    html = f"""
    <div style="
        position: fixed; 
        top: 20px; 
        right: 20px; 
        z-index: 1000; 
        background: white; 
        padding: 10px; 
        border: 2px solid grey; 
        border-radius: 5px; 
        max-width: 300px; 
        max-height: 500px; 
        overflow-y: auto;
        font-family: Arial, sans-serif;
    ">
        <h4 style="margin: 0 0 10px 0; color: #333;">Crime Summary (Mar 1 - Apr 1: {len(df)})</h4>
        
        <h4 style="margin: 10px 0 5px 0; color: #333;">By Incident Type</h4>
        <table style="width: 100%; margin-bottom: 10px;">
            <tr style="background: #f0f0f0;">
                <th style="padding: 5px;">Type</th>
                <th style="padding: 5px;">Count</th>
            </tr>
            {"".join([
                f'<tr><td style="padding: 5px;">{row["Incident Type"]}</td><td style="padding: 5px;">{row.Count}</td></tr>'
                for _, row in incident_counts.iterrows()
            ])}
        </table>
        
        {time_html}
    </div>
    """
    return html

# ============================================================================
# MAIN EXECUTION WITH DEBUGGING
# ============================================================================
if __name__ == "__main__":
    # Fetch and prepare data
    df = fetch_crime_data()
    
    # Debugging output
    print("\nFirst 5 rows of data:")
    print(df[['incident_type', 'block_address', 'occurred_datetime']].head())
    print("\nMissing values per column:")
    print(df.isnull().sum())

    # Date filtering
    if 'occurred_datetime' in df.columns:
        df['occurred_datetime'] = pd.to_datetime(df['occurred_datetime'], errors='coerce')
        start_date = pd.Timestamp('2024-03-01')
        end_date = pd.Timestamp('2024-04-02')
        df = df[(df['occurred_datetime'] >= start_date) & (df['occurred_datetime'] < end_date)]
    
    print(f"\nFiltered cases between March 1 and April 1: {len(df)}")

    if df.empty:
        print("No data found")
        exit()

    # Geocode addresses
    geocoder = Geocoder()
    df = df.dropna(subset=['block_address'])
    unique_addresses = df['block_address'].unique()
    
    address_coords = {}
    for address in tqdm(unique_addresses, desc="Geocoding"):
        coords = geocoder.get_coords(address)
        if coords:
            address_coords[address] = coords
    
    geocoder._save_cache()

    # Process coordinates
    df['coords'] = df['block_address'].map(address_coords)
    df = df.dropna(subset=['coords'])
    df[['latitude', 'longitude']] = pd.DataFrame(df['coords'].tolist(), index=df.index)

    # Create map
    m = folium.Map(location=[37.87, -122.27], zoom_start=14, tiles='CartoDB positron')

    # Add components
    incident_summary = create_incident_summary(df)
    m.get_root().html.add_child(folium.Element(incident_summary))

    crime_list = create_crime_list(df)
    m.get_root().html.add_child(folium.Element(crime_list))

    # Heatmap
    HeatMap(
        df[['latitude', 'longitude']].values,
        radius=12,
        blur=15,
        min_opacity=0.5
    ).add_to(m)

    # Street segments
    G = get_street_network()
    edge_counts = process_spatial_data(df, G)
    gdf_edges = ox.graph_to_gdfs(G, nodes=False)
    
    for (u, v, k), count in edge_counts.items():
        try:
            edge_data = gdf_edges.loc[(u, v, k)]
            folium.GeoJson(
                edge_data.geometry,
                style_function=lambda x, count=count: {
                    'color': '#ff0000' if count > 3 else '#ffa500',
                    'weight': 4 + count//2,
                    'opacity': 0.7
                },
                tooltip=f"Crimes: {count}"
            ).add_to(m)
        except KeyError:
            continue

    # Disclaimer
    disclaimer = f"""
    <div style="
        position: fixed; 
        bottom: 20px; 
        left: 20px; 
        z-index: 1000; 
        background: white; 
        padding: 10px; 
        border: 2px solid grey; 
        border-radius: 5px; 
        max-width: 300px;
        font-size: 12px;
    ">
        <b>Note:</b> Data from Berkeley PD (March 1 - April 1 2024)<br>
        Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
        Source: <a href="https://data.cityofberkeley.info/" target="_blank">Berkeley Open Data</a>
    </div>
    """
    
    m.get_root().html.add_child(folium.Element(disclaimer))

    m.save("berkeley_crime_analysis.html")
    print("Map successfully generated with crime data")
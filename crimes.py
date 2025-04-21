import json
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster, HeatMap
from shapely.geometry import Polygon
import numpy as np
from branca.colormap import LinearColormap

# ========================================================================
# 1. CACHED DATA LOADING (UPDATED)
# ========================================================================
class CrimeDataLoader:
    def __init__(self):
        # Load cached data
        with open('geocode_cache.json') as f:
            self.cache = json.load(f)
            
        self.df = pd.read_csv('cached_crime_data.csv')
        self.df[['lat', 'lon']] = self.df['Block_Address'].apply(
            lambda x: pd.Series(self.cache.get(f"{x}, Berkeley, CA", (None, None)))
        )
        self.df = self.df.dropna().drop_duplicates(subset=['lat', 'lon'])
        
        # Load street data with proper CRS
        self.streets = gpd.read_file('berkeley_streets.gpkg')
        self.streets = self.streets.to_crs(epsg=4326)

# ========================================================================
# 2. UPDATED VISUALIZATION SYSTEM WITH HEATMAP
# ========================================================================
class CrimeVisualizer:
    def __init__(self, data_loader):
        self.data = data_loader
        self.map = folium.Map(location=[37.87, -122.27], zoom_start=12, control_scale=True)
        
        # Create colormaps
        self.area_colormap = LinearColormap(
            ['green', 'yellow', 'red'],
            vmin=0, vmax=self.data.df.shape[0]//10
        )
        
        # Add layers
        self.heatmap = HeatMap(
            data=self.data.df[['lat', 'lon']].values,
            radius=15,
            blur=20,
            max_zoom=13,
            gradient={0.4: 'blue', 0.6: 'lime', 0.8: 'yellow', 1: 'red'}
        )
        
        self.street_layer = folium.FeatureGroup(name='Street View')
        self.marker_cluster = MarkerCluster().add_to(self.map)

    def create_street_heatmap(self):
        """Create street-level visualization"""
        # Spatial join between crimes and streets
        crime_points = gpd.GeoDataFrame(
            self.data.df,
            geometry=gpd.points_from_xy(self.data.df.lon, self.data.df.lat)
        )
        
        joined = gpd.sjoin(crime_points, self.data.streets, predicate='within')
        crime_counts = joined.groupby('index_right').size()
        
        # Add street layer
        folium.GeoJson(
            self.data.streets,
            style_function=lambda feature: {
                'color': self.area_colormap(crime_counts.get(feature.id, 0)),
                'weight': 3 + (crime_counts.get(feature.id, 0) ** 0.5),
                'opacity': 0.7
            },
            name='Street Crime Density'
        ).add_to(self.street_layer)

    def add_controls(self):
        """Add layer controls"""
        self.heatmap.add_to(self.map)
        self.map.add_child(self.street_layer)
        folium.LayerControl().add_to(self.map)

    def add_markers(self):
        """Add crime markers"""
        for _, row in self.data.df.iterrows():
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=3,
                color='black',
                fill=True,
                fill_opacity=0.6
            ).add_to(self.marker_cluster)

    def render(self):
        self.create_street_heatmap()
        self.add_markers()
        self.add_controls()
        return self.map

# ========================================================================
# 3. EXECUTION FLOW
# ========================================================================
if __name__ == '__main__':
    loader = CrimeDataLoader()
    visualizer = CrimeVisualizer(loader)
    m = visualizer.render()
    m.save('crime_visualization.html')
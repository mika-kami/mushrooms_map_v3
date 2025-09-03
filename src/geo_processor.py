import os
import json
import numpy as np
from PIL import Image
from typing import List, Tuple, Dict, Optional
from datetime import datetime
from sklearn.cluster import DBSCAN
from scipy import ndimage
from src.config import (
    CZECH_BOUNDS,
    IMAGE_BOUNDS,
    GEOJSON_DIR,
    KML_DIR,
    MIN_FEATURE_AREA,
    COORDINATE_SYSTEM,
    OUTPUT_FORMATS
)
from src.kml_processor import KMLProcessor  # Import KML processor


class GeoProcessor:
    """
    Handles geographic coordinate mapping and processing for Czech Republic mushroom maps.
    Converts pixel coordinates to real-world geographic coordinates (WGS84).
    Now includes KML export functionality.
    """

    def __init__(self):
        self.czech_bounds = CZECH_BOUNDS
        self.image_bounds = IMAGE_BOUNDS
        self.kml_processor = KMLProcessor()  # Initialize KML processor

    def update_image_bounds(self, image: Image.Image):
        """
        Update image bounds based on the actual image dimensions.
        This should be called when processing the first image.
        """
        self.image_bounds["width"] = image.width
        self.image_bounds["height"] = image.height
        print(f"Updated image bounds: {image.width}x{image.height}")

    def pixel_to_coordinates(self, x: int, y: int) -> Tuple[float, float]:
        """
        Convert pixel coordinates to geographic coordinates (longitude, latitude).

        Args:
            x: Pixel x-coordinate (column)
            y: Pixel y-coordinate (row)

        Returns:
            Tuple of (longitude, latitude) in WGS84 coordinates
        """
        if not self.image_bounds["width"] or not self.image_bounds["height"]:
            raise ValueError("Image bounds not set. Call update_image_bounds() first.")

        # Calculate longitude (x-axis mapping)
        lon_range = self.czech_bounds["east"] - self.czech_bounds["west"]
        longitude = self.czech_bounds["west"] + (x / self.image_bounds["width"]) * lon_range

        # Calculate latitude (y-axis mapping, inverted because image y=0 is top)
        lat_range = self.czech_bounds["north"] - self.czech_bounds["south"]
        latitude = self.czech_bounds["north"] - (y / self.image_bounds["height"]) * lat_range

        return longitude, latitude

    def coordinates_to_pixel(self, longitude: float, latitude: float) -> Tuple[int, int]:
        """
        Convert geographic coordinates to pixel coordinates.

        Args:
            longitude: Longitude in WGS84
            latitude: Latitude in WGS84

        Returns:
            Tuple of (x, y) pixel coordinates
        """
        if not self.image_bounds["width"] or not self.image_bounds["height"]:
            raise ValueError("Image bounds not set. Call update_image_bounds() first.")

        # Calculate x pixel coordinate
        lon_range = self.czech_bounds["east"] - self.czech_bounds["west"]
        x = int(((longitude - self.czech_bounds["west"]) / lon_range) * self.image_bounds["width"])

        # Calculate y pixel coordinate (inverted)
        lat_range = self.czech_bounds["north"] - self.czech_bounds["south"]
        y = int(((self.czech_bounds["north"] - latitude) / lat_range) * self.image_bounds["height"])

        return x, y

    def extract_highlighted_regions(self, image: Image.Image) -> List[np.ndarray]:
        """
        Extract connected regions of highlighted pixels from the processed image.
        Uses multiple methods to detect highlighted areas.

        Args:
            image: Processed PIL Image with highlighted areas

        Returns:
            List of numpy arrays, each containing pixel coordinates of a connected region
        """
        # Convert image to numpy array
        img_array = np.array(image)
        print(f"Image shape: {img_array.shape}")

        # Method 1: Detect pure blue pixels (HIGHLIGHT_COLOR = (0, 0, 255))
        blue_mask = (img_array[:, :, 0] < 50) & (img_array[:, :, 1] < 50) & (img_array[:, :, 2] > 200)
        blue_count = np.sum(blue_mask)
        print(f"Method 1 - Pure blue pixels found: {blue_count}")

        # Method 2: Detect any strongly blue-dominant pixels
        blue_dominant_mask = (img_array[:, :, 2] > img_array[:, :, 0] + 100) & (
                    img_array[:, :, 2] > img_array[:, :, 1] + 100)
        blue_dominant_count = np.sum(blue_dominant_mask)
        print(f"Method 2 - Blue-dominant pixels found: {blue_dominant_count}")

        # Method 3: Detect darkened areas (areas processed by the comparison algorithm)
        # These areas should be darker than the original image
        gray = np.mean(img_array, axis=2)
        dark_mask = gray < 150  # Adjust threshold as needed
        dark_count = np.sum(dark_mask)
        print(f"Method 3 - Dark pixels found: {dark_count}")

        # Method 4: Check for green areas (original mushroom probability colors)
        green_high = np.array([176, 221, 156])  # HIGH_PROB_RGB
        green_very_high = np.array([112, 189, 143])  # VERY_HIGH_PROB_RGB

        # Check for green areas with tolerance
        green_tolerance = 30
        green_mask_high = np.all(np.abs(img_array - green_high) <= green_tolerance, axis=2)
        green_mask_very_high = np.all(np.abs(img_array - green_very_high) <= green_tolerance, axis=2)
        green_mask = green_mask_high | green_mask_very_high
        green_count = np.sum(green_mask)
        print(f"Method 4 - Green mushroom pixels found: {green_count}")

        # Combine all detection methods - use the one with most results
        detection_methods = [
            ("blue", blue_mask, blue_count),
            ("blue_dominant", blue_dominant_mask, blue_dominant_count),
            ("dark", dark_mask, dark_count),
            ("green", green_mask, green_count)
        ]

        # Use the method that found the most pixels, but prefer blue methods for highlighted areas
        if blue_count > 0:
            final_mask = blue_mask
            method_used = "blue"
        elif blue_dominant_count > 0:
            final_mask = blue_dominant_mask
            method_used = "blue_dominant"
        elif green_count > 0:
            final_mask = green_mask
            method_used = "green"
        elif dark_count > 0:
            final_mask = dark_mask
            method_used = "dark"
        else:
            print("No highlighted areas detected with any method!")
            return []

        print(f"Using detection method: {method_used}")

        # Label connected components
        labeled_array, num_features = ndimage.label(final_mask)
        print(f"Found {num_features} connected components")

        regions = []
        for i in range(1, num_features + 1):
            # Get coordinates of pixels in this region
            region_coords = np.where(labeled_array == i)
            region_pixels = np.column_stack((region_coords[1], region_coords[0]))  # (x, y) format

            print(f"Region {i}: {len(region_pixels)} pixels")

            # Use a lower threshold for minimum feature area
            min_area = max(MIN_FEATURE_AREA // 10, 10)  # More lenient minimum area
            if len(region_pixels) >= min_area:
                regions.append(region_pixels)
                print(f"Region {i} accepted (size: {len(region_pixels)})")
            else:
                print(f"Region {i} rejected (too small: {len(region_pixels)} < {min_area})")

        print(f"Final regions accepted: {len(regions)}")
        return regions

    def cluster_regions(self, regions: List[np.ndarray], eps: float = 50, min_samples: int = 5) -> List[np.ndarray]:
        """
        Group nearby regions using DBSCAN clustering.
        Made more lenient for better detection.

        Args:
            regions: List of pixel coordinate arrays
            eps: Maximum distance between samples for clustering (increased)
            min_samples: Minimum samples in a cluster (decreased)

        Returns:
            List of clustered regions
        """
        if not regions:
            print("No regions to cluster")
            return []

        # If we have few regions, don't cluster - return as is
        if len(regions) <= 3:
            print(f"Too few regions ({len(regions)}) to cluster, returning as is")
            return regions

        # Combine all regions and track their origins
        all_points = []
        region_labels = []

        for i, region in enumerate(regions):
            all_points.extend(region)
            region_labels.extend([i] * len(region))

        all_points = np.array(all_points)
        print(f"Clustering {len(all_points)} total points from {len(regions)} regions")

        # Apply DBSCAN clustering
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(all_points)

        # Group points by cluster
        clustered_regions = []
        unique_labels = set(clustering.labels_)
        print(f"DBSCAN found {len(unique_labels)} clusters (including noise)")

        for label in unique_labels:
            if label == -1:  # Skip noise points
                continue

            cluster_mask = clustering.labels_ == label
            cluster_points = all_points[cluster_mask]
            clustered_regions.append(cluster_points)
            print(f"Cluster {label}: {len(cluster_points)} points")

        print(f"Final clustered regions: {len(clustered_regions)}")
        return clustered_regions

    def create_polygon_from_region(self, region: np.ndarray) -> List[Tuple[float, float]]:
        """
        Create a polygon outline from a region of pixels.

        Args:
            region: Numpy array of pixel coordinates

        Returns:
            List of (longitude, latitude) tuples forming a polygon
        """
        # Find convex hull of the region
        from scipy.spatial import ConvexHull

        if len(region) < 3:
            print(f"Region too small for polygon: {len(region)} points")
            return []

        try:
            hull = ConvexHull(region)
            hull_points = region[hull.vertices]

            # Convert to geographic coordinates
            geo_coords = []
            for x, y in hull_points:
                lon, lat = self.pixel_to_coordinates(int(x), int(y))
                geo_coords.append((lon, lat))

            # Close the polygon by adding the first point at the end
            if geo_coords and geo_coords[0] != geo_coords[-1]:
                geo_coords.append(geo_coords[0])

            print(f"Created polygon with {len(geo_coords)} vertices")
            return geo_coords

        except Exception as e:
            print(f"Error creating polygon: {e}")
            return []

    def regions_to_geojson(self, regions: List[np.ndarray], date_str: str) -> Dict:
        """
        Convert regions to GeoJSON format.

        Args:
            regions: List of pixel coordinate arrays
            date_str: Date string for metadata

        Returns:
            GeoJSON dictionary
        """
        features = []

        for i, region in enumerate(regions):
            polygon_coords = self.create_polygon_from_region(region)

            if len(polygon_coords) >= 4:  # Minimum for a valid polygon
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [polygon_coords]
                    },
                    "properties": {
                        "id": i,
                        "date": date_str,
                        "area_pixels": len(region),
                        "mushroom_probability": "very_high",
                        "created": datetime.now().isoformat()
                    }
                }
                features.append(feature)
                print(f"Created GeoJSON feature {i} with {len(polygon_coords)} coordinates")

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "date": date_str,
                "coordinate_system": COORDINATE_SYSTEM,
                "source": "Czech Hydrometeorological Institute",
                "bounds": self.czech_bounds,
                "total_features": len(features),
                "processing_timestamp": datetime.now().isoformat()
            }
        }

        print(f"Created GeoJSON with {len(features)} features")
        return geojson

    def process_image_to_geojson(self, image_path: str, date_str: str) -> Optional[str]:
        """
        Process a complete image to GeoJSON format and optionally convert to KML.

        Args:
            image_path: Path to the processed image
            date_str: Date string for the image

        Returns:
            Path to the saved GeoJSON file, or None if processing failed
        """
        try:
            print(f"Processing image to GeoJSON: {image_path}")

            # Load and process image
            image = Image.open(image_path).convert("RGB")
            self.update_image_bounds(image)

            # Extract highlighted regions
            regions = self.extract_highlighted_regions(image)
            print(f"Extracted {len(regions)} initial regions")

            if len(regions) == 0:
                print("No regions found - creating empty GeoJSON")
                geojson_data = self.regions_to_geojson([], date_str)
            else:
                # Cluster nearby regions (with more lenient settings)
                clustered_regions = self.cluster_regions(regions, eps=30, min_samples=3)
                print(f"Clustered into {len(clustered_regions)} final regions")

                # Convert to GeoJSON
                geojson_data = self.regions_to_geojson(clustered_regions, date_str)

            # Save GeoJSON file
            geojson_filename = f"mushroom_areas_{date_str}.geojson"
            geojson_path = os.path.join(GEOJSON_DIR, geojson_filename)

            with open(geojson_path, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, indent=2, ensure_ascii=False)

            print(f"GeoJSON saved: {geojson_path}")

            # Also create KML file if GeoJSON has features
            if geojson_data.get("features"):
                kml_path = self.kml_processor.process_geojson_to_kml(geojson_path, date_str)
                if kml_path:
                    print(f"KML file also created: {kml_path}")
                else:
                    print("Failed to create KML file")
            else:
                print("No features to convert to KML")

            return geojson_path

        except Exception as e:
            print(f"Error processing image to GeoJSON: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_region_info(self, longitude: float, latitude: float, geojson_path: str) -> Optional[Dict]:
        """
        Get information about a specific geographic location.

        Args:
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            geojson_path: Path to GeoJSON file

        Returns:
            Dictionary with region information, or None if not found
        """
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                geojson_data = json.load(f)

            # Check if point is within any polygon
            from shapely.geometry import Point, Polygon

            point = Point(longitude, latitude)

            for feature in geojson_data['features']:
                if feature['geometry']['type'] == 'Polygon':
                    coords = feature['geometry']['coordinates'][0]
                    polygon = Polygon(coords)

                    if polygon.contains(point):
                        return {
                            "found": True,
                            "properties": feature['properties'],
                            "coordinates": [longitude, latitude]
                        }

            return {"found": False, "coordinates": [longitude, latitude]}

        except Exception as e:
            print(f"Error checking region info: {e}")
            return None

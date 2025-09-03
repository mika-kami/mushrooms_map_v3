import os
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Dict, List, Optional
from datetime import datetime
from src.config import KML_DIR, KML_STYLES


class KMLProcessor:
    """
    Handles conversion from GeoJSON to KML format for Czech Republic mushroom maps.
    Creates KML files compatible with Google Earth and other mapping applications.
    """

    def __init__(self):
        self.kml_styles = KML_STYLES

    def create_kml_style(self, style_id: str, style_config: Dict) -> ET.Element:
        """
        Create a KML style element.

        Args:
            style_id: Unique identifier for the style
            style_config: Style configuration dictionary

        Returns:
            KML Style element
        """
        style = ET.Element("Style", id=style_id)

        # Line style
        line_style = ET.SubElement(style, "LineStyle")
        line_color = ET.SubElement(line_style, "color")
        line_color.text = style_config.get("color", "ffffff00")
        line_width = ET.SubElement(line_style, "width")
        line_width.text = str(style_config.get("line_width", 1))

        # Polygon style
        poly_style = ET.SubElement(style, "PolyStyle")
        poly_color = ET.SubElement(poly_style, "color")
        poly_color.text = style_config.get("fill_color", "77ffffff")
        poly_fill = ET.SubElement(poly_style, "fill")
        poly_fill.text = "1"
        poly_outline = ET.SubElement(poly_style, "outline")
        poly_outline.text = "1"

        return style

    def create_kml_placemark(self, feature: Dict, feature_id: int) -> ET.Element:
        """
        Create a KML placemark from a GeoJSON feature.

        Args:
            feature: GeoJSON feature dictionary
            feature_id: Unique identifier for the feature

        Returns:
            KML Placemark element
        """
        placemark = ET.Element("Placemark")

        # Name
        name = ET.SubElement(placemark, "name")
        name.text = f"Mushroom Area {feature_id + 1}"

        # Description
        description = ET.SubElement(placemark, "description")
        props = feature.get("properties", {})
        desc_text = f"""<![CDATA[
        <h3>Mushroom Probability Area</h3>
        <table border="1" cellpadding="5">
        <tr><td><b>Date:</b></td><td>{props.get('date', 'Unknown')}</td></tr>
        <tr><td><b>Probability:</b></td><td>{props.get('mushroom_probability', 'Unknown')}</td></tr>
        <tr><td><b>Area (pixels):</b></td><td>{props.get('area_pixels', 'Unknown')}</td></tr>
        <tr><td><b>Region ID:</b></td><td>{props.get('id', 'Unknown')}</td></tr>
        <tr><td><b>Created:</b></td><td>{props.get('created', 'Unknown')}</td></tr>
        </table>
        <p>This area shows high probability for mushroom occurrence based on Czech Hydrometeorological Institute data.</p>
        ]]>"""
        description.text = desc_text

        # Style reference
        style_url = ET.SubElement(placemark, "styleUrl")
        probability = props.get("mushroom_probability", "default")
        style_url.text = f"#{probability}_style"

        # Geometry
        geometry = feature.get("geometry", {})
        if geometry.get("type") == "Polygon":
            self._add_polygon_geometry(placemark, geometry)

        return placemark

    def _add_polygon_geometry(self, placemark: ET.Element, geometry: Dict):
        """
        Add polygon geometry to a KML placemark.

        Args:
            placemark: KML Placemark element
            geometry: GeoJSON geometry dictionary
        """
        polygon = ET.SubElement(placemark, "Polygon")

        # Tessellate (for following terrain)
        tessellate = ET.SubElement(polygon, "tessellate")
        tessellate.text = "1"

        # Altitude mode
        altitude_mode = ET.SubElement(polygon, "altitudeMode")
        altitude_mode.text = "clampToGround"

        # Outer boundary
        outer_boundary = ET.SubElement(polygon, "outerBoundaryIs")
        linear_ring = ET.SubElement(outer_boundary, "LinearRing")
        coordinates = ET.SubElement(linear_ring, "coordinates")

        # Convert coordinates to KML format (lon,lat,alt)
        coord_list = []
        for coord_pair in geometry["coordinates"][0]:
            lon, lat = coord_pair
            coord_list.append(f"{lon},{lat},0")

        coordinates.text = " ".join(coord_list)

    def geojson_to_kml(self, geojson_path: str, output_path: str) -> bool:
        """
        Convert a GeoJSON file to KML format.

        Args:
            geojson_path: Path to input GeoJSON file
            output_path: Path for output KML file

        Returns:
            True if conversion successful, False otherwise
        """
        try:
            # Load GeoJSON data
            with open(geojson_path, 'r', encoding='utf-8') as f:
                geojson_data = json.load(f)

            # Create KML root element
            kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
            document = ET.SubElement(kml, "Document")

            # Document name and description
            name = ET.SubElement(document, "name")
            metadata = geojson_data.get("metadata", {})
            date_str = metadata.get("date", "Unknown")
            name.text = f"Czech Republic Mushroom Areas - {date_str}"

            description = ET.SubElement(document, "description")
            desc_text = f"""<![CDATA[
            <h2>Mushroom Probability Map</h2>
            <p><b>Date:</b> {date_str}</p>
            <p><b>Source:</b> {metadata.get('source', 'Czech Hydrometeorological Institute')}</p>
            <p><b>Total Areas:</b> {metadata.get('total_features', 0)}</p>
            <p><b>Coordinate System:</b> {metadata.get('coordinate_system', 'WGS84')}</p>
            <p><b>Generated:</b> {metadata.get('processing_timestamp', datetime.now().isoformat())}</p>
            <br/>
            <p>This map shows areas with high probability of mushroom occurrence in the Czech Republic.</p>
            ]]>"""
            description.text = desc_text

            # Add styles
            for style_name, style_config in self.kml_styles.items():
                style_element = self.create_kml_style(f"{style_name}_style", style_config)
                document.append(style_element)

            # Add folder for organizing placemarks
            folder = ET.SubElement(document, "Folder")
            folder_name = ET.SubElement(folder, "name")
            folder_name.text = f"Mushroom Areas ({date_str})"

            folder_desc = ET.SubElement(folder, "description")
            folder_desc.text = f"High probability mushroom areas detected on {date_str}"

            # Convert features to placemarks
            features = geojson_data.get("features", [])
            for i, feature in enumerate(features):
                placemark = self.create_kml_placemark(feature, i)
                folder.append(placemark)

            # Write KML file
            self._write_pretty_kml(kml, output_path)
            print(f"KML file created: {output_path}")
            return True

        except Exception as e:
            print(f"Error converting GeoJSON to KML: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _write_pretty_kml(self, kml_element: ET.Element, output_path: str):
        """
        Write KML with pretty formatting.

        Args:
            kml_element: Root KML element
            output_path: Output file path
        """
        # Convert to string
        rough_string = ET.tostring(kml_element, encoding='unicode')

        # Pretty print
        reparsed = minidom.parseString(rough_string)
        pretty_string = reparsed.toprettyxml(indent="  ")

        # Remove empty lines and fix XML declaration
        lines = [line for line in pretty_string.split('\n') if line.strip()]
        if lines[0].startswith('<?xml'):
            lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def process_geojson_to_kml(self, geojson_path: str, date_str: str) -> Optional[str]:
        """
        Process a GeoJSON file and create corresponding KML file.

        Args:
            geojson_path: Path to GeoJSON file
            date_str: Date string for naming

        Returns:
            Path to created KML file, or None if failed
        """
        try:
            kml_filename = f"mushroom_areas_{date_str}.kml"
            kml_path = os.path.join(KML_DIR, kml_filename)

            if self.geojson_to_kml(geojson_path, kml_path):
                return kml_path
            else:
                return None

        except Exception as e:
            print(f"Error processing GeoJSON to KML: {e}")
            return None

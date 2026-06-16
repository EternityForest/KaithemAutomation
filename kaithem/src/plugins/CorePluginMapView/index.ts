import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { LayerControl } from "maplibre-gl-layer-control";
import "maplibre-gl-layer-control/style.css";
import MaplibreGeocoder from "@maplibre/maplibre-gl-geocoder";
import "@maplibre/maplibre-gl-geocoder/dist/maplibre-gl-geocoder.css";

// Wait for DOM
document.addEventListener("DOMContentLoaded", async () => {


  // Define tile sources - using Kaithem's internal tile server
  const sources: Record<string, maplibregl.SourceSpecification> = {
    osm: {
      type: "raster",
      tiles: ["/maptiles/tile/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
    usgs: {
      type: "raster",
      tiles: ["/maptiles/tile/{z}/{x}/{y}?map=usgs"],
      tileSize: 256,
      attribution:
        'Tiles courtesy of the <a href="https://usgs.gov/">U.S. Geological Survey</a>',
      maxzoom: 16,
    },
  };

  // Define layers using the layer-control format
  const layers = [
    {
      id: "usgs-layer",
      source: "usgs",
      type: "raster" as const,
      name: "USGS Imagery/Topo",
    },
    {
      id: "osm-layer",
      source: "osm",
      type: "raster" as const,
      name: "OpenStreetMap",
    },
  ];

  // Create the map
  const map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: sources,
      layers: layers,
      terrain: undefined,
      sky: undefined,
    },
    center: [-0.09, 51.505], // Default: London
    zoom: 6,
    attributionControl: {
      compact: true,
    },
  });

  // Add navigation control (zoom buttons)
  map.addControl(new maplibregl.NavigationControl(), "top-right");

  // Add geolocate control (go to current position)
  const geolocateControl = new maplibregl.GeolocateControl({
    positionOptions: {
      enableHighAccuracy: true,
      timeout: 6000,
      maximumAge: 0,
    },
    trackUserLocation: false,
  });
  map.addControl(geolocateControl, "top-right");

  // Add layer control for switching between map layers
  const layerControl = new LayerControl({
  });
  map.addControl(layerControl, "top-left");


  const geocoderApi = {
    forwardGeocode: async (config) => {
        const features = [];
        try {
            const request =
        `https://nominatim.openstreetmap.org/search?q=${
            config.query
        }&format=geojson&polygon_geojson=1&addressdetails=1`;
            const response = await fetch(request);
            const geojson = await response.json();
            for (const feature of geojson.features) {
                const center = [
                    feature.bbox[0] +
                (feature.bbox[2] - feature.bbox[0]) / 2,
                    feature.bbox[1] +
                (feature.bbox[3] - feature.bbox[1]) / 2
                ];
                const point = {
                    type: 'Feature',
                    geometry: {
                        type: 'Point',
                        coordinates: center
                    },
                    place_name: feature.properties.display_name,
                    properties: feature.properties,
                    text: feature.properties.display_name,
                    place_type: ['place'],
                    center
                };
                features.push(point);
            }
        } catch (e) {
            console.error(`Failed to forwardGeocode with error: ${e}`);
        }

        return {
            features
        };
    }
  };
  
  // Add geocoder for location search
  const geocoder = new MaplibreGeocoder(geocoderApi, {maplibregl});
  map.addControl(geocoder as unknown as maplibregl.IControl, "top-left");

  // Handle click to show coordinates
  map.on("click", (e) => {
    const coordinates: [number, number] = [e.lngLat.lng, e.lngLat.lat];
    const message = `Coordinates: ${coordinates[1].toFixed(6)}, ${coordinates[0].toFixed(6)}`;

    // Create a popup at the click location
    new maplibregl.Popup()
      .setLngLat(coordinates)
      .setHTML(message)
      .addTo(map);

    // Also log to console for easy access
    console.log("Clicked coordinates:", message);
  });

  // Change cursor on hover over clickable elements
  map.on("mouseenter", "osm-layer", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "osm-layer", () => {
    map.getCanvas().style.cursor = "";
  });

  // Ensure map renders correctly when container is shown
  map.on("load", () => {
    map.resize();
  });

  // Handle window resize
  window.addEventListener("resize", () => {
    map.resize();
  });
});
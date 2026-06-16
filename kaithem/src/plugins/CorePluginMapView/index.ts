import maplibregl from "maplibre-gl";
import { LayerControl } from "maplibre-gl-layer-control";
import MaplibreGeocoder from "@maplibre/maplibre-gl-geocoder";
import "@maplibre/maplibre-gl-geocoder/dist/maplibre-gl-geocoder.css";

// Import Maplibre CSS - using Vite's ?url import for CSS
import maplibreCss from "maplibre-gl/dist/maplibre-gl.css?url";



// Wait for DOM
document.addEventListener("DOMContentLoaded", async () => {
  // Load Maplibre CSS
  await loadMaplibreCSS();

  // Define tile sources - using Kaithem's internal tile server
  const sources: Record<string, maplibregl.AnySourceSpec> = {
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
      id: "osm-layer",
      source: "osm",
      type: "raster" as const,
      name: "OpenStreetMap",
    },
    {
      id: "usgs-layer",
      source: "usgs",
      type: "raster" as const,
      name: "USGS Imagery/Topo",
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
    attributionControl: true,
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
    showUserHeading: true,
    showUserAccuracyCircle: true,
  });
  map.addControl(geolocateControl, "top-right");

  // Add layer control for switching between map layers
  const layerControl = new LayerControl({
    layers: layers,
    publicId: "map-layers",
  });
  map.addControl(layerControl, "top-left");

  // Add geocoder for location search
  const geocoder = new MaplibreGeocoder(maplibregl, {
    maplibregl: maplibregl,
    placeholder: "Search for a location",
    showResultMarkers: true,
    showPoweredBy: false,
    reverseGeocode: false,
  });
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
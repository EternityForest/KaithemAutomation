import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { LayerControl } from 'maplibre-gl-layer-control';
import 'maplibre-gl-layer-control/style.css';
import MaplibreGeocoder from '@maplibre/maplibre-gl-geocoder';
import '@maplibre/maplibre-gl-geocoder/dist/maplibre-gl-geocoder.css';
import MaplibreMeasures from 'maplibre-gl-measures';

// Wait for DOM
document.addEventListener('DOMContentLoaded', async () => {
  // Fetch tilejson configuration from server
  const tilejsonResponse = await fetch('/maptiles/tilejson');
  const tilejsonData = await tilejsonResponse.json();

  // Build sources and layers from TileJSON config
  const maplibreSources: Record<string, maplibregl.SourceSpecification> = {};
  const maplibreLayers: Array<{
    id: string;
    source: string;
    type: 'raster';
    name: string;
    layout?: Record<string, unknown>;
  }> = [];

  const layerStates: Record<
    string,
    { visible: boolean; opacity: number; name: string }
  > = {};

  for (const [mapName, tilejson] of Object.entries(tilejsonData)) {
    const tj = tilejson as {
      name: string;
      attribution: string;
      tiles: string[];
      minzoom: number;
      maxzoom: number;
      type: string;
    };

    if (tj.type !== 'raster') {
      continue;
    }

    layerStates[`${mapName}-layer`] = {
      visible: false,
      opacity: 1,
      name: tj.name || mapName,
    };

    maplibreSources[mapName] = {
      type: 'raster',
      tiles: tj.tiles,
      tileSize: 256,
      attribution: tj.attribution,
      minzoom: tj.minzoom,
      maxzoom: tj.maxzoom,
    };

    maplibreLayers.push({
      id: `${mapName}-layer`,
      source: mapName,
      type: 'raster' as const,
      name: tj.name || mapName,
      layout: {
        visibility: mapName === 'openstreetmap' ? 'visible' : 'none',
      },
    });
  }

  maplibreSources['mapterhorn'] = {
    type: 'raster-dem',
    attribution: tilejsonData.mapterhorn.attribution,
    tiles: tilejsonData.mapterhorn.tiles,
  }

  // Create the map
  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: maplibreSources,
      layers: maplibreLayers,
      terrain: {
        source: 'mapterhorn',
        exaggeration: 1,
      },
      sky: undefined,
    },
    center: [-0.09, 51.505], // Default: London
    zoom: 6,
    attributionControl: {
      compact: true,
    },
  });

  // Add navigation control (zoom buttons)
  map.addControl(
    new maplibregl.NavigationControl({
      showCompass: true,
      showZoom: true,
      visualizePitch: true,
    }),
    'top-right'
  );

  // map.addControl(
  //   new maplibregl.TerrainControl({
  //     source: 'terrainSource',
  //     exaggeration: 1,
  //   })
  // );

  // Add geolocate control (go to current position)
  const geolocateControl = new maplibregl.GeolocateControl({
    positionOptions: {
      enableHighAccuracy: true,
      timeout: 6000,
      maximumAge: 0,
    },
    trackUserLocation: false,
  });
  map.addControl(geolocateControl, 'top-right');

  layerStates['openstreetmap-layer'] = {
    visible: true,
    opacity: 1,
    name: 'OpenStreetMap',
  };
  // Add layer control for switching between map layers
  const layerControl = new LayerControl({
    layerStates: layerStates,
    showStyleEditor: false,
    panelMinWidth: 350,
    panelMaxWidth: 350,
    panelWidth: 350,
  });
  map.addControl(layerControl, 'top-left');

  const geocoderApi = {
    forwardGeocode: async (config) => {
      const features = [];
      try {
        const request = `https://nominatim.openstreetmap.org/search?q=${
          config.query
        }&format=geojson&polygon_geojson=1&addressdetails=1`;
        const response = await fetch(request);
        const geojson = await response.json();
        for (const feature of geojson.features) {
          const center = [
            feature.bbox[0] + (feature.bbox[2] - feature.bbox[0]) / 2,
            feature.bbox[1] + (feature.bbox[3] - feature.bbox[1]) / 2,
          ];
          const point = {
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: center,
            },
            place_name: feature.properties.display_name,
            properties: feature.properties,
            text: feature.properties.display_name,
            place_type: ['place'],
            center,
          };
          features.push(point);
        }
      } catch (e) {
        console.error(`Failed to forwardGeocode with error: ${e}`);
      }

      return {
        features,
      };
    },
  };

  // Add geocoder for location search
  const geocoder = new MaplibreGeocoder(geocoderApi, { maplibregl });
  map.addControl(geocoder as unknown as maplibregl.IControl, 'top-left');

  // Add measures control for distance/area measurements
  const measuresControl = new MaplibreMeasures({ maplibregl });
  map.addControl(measuresControl, 'top-right');

  // Handle click to show coordinates
  map.on('click', (e) => {
    const coordinates: [number, number] = [e.lngLat.lng, e.lngLat.lat];
    const message = `Coordinates: ${coordinates[1].toFixed(6)}, ${coordinates[0].toFixed(6)}`;

    // Create a popup at the click location
    new maplibregl.Popup().setLngLat(coordinates).setHTML(message).addTo(map);

    // Also log to console for easy access
    console.log('Clicked coordinates:', message);
  });

  // Change cursor on hover over clickable elements
  map.on('mouseenter', 'osm-layer', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'osm-layer', () => {
    map.getCanvas().style.cursor = '';
  });

  // Ensure map renders correctly when container is shown
  map.on('load', () => {
    map.resize();
  });

  // Handle window resize
  window.addEventListener('resize', () => {
    map.resize();
  });
});

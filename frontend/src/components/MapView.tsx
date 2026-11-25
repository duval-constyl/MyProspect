import "maplibre-gl/dist/maplibre-gl.css";

import { type GeoJSONSource, Map as MapLibreMap, type MapLayerMouseEvent, setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef } from "react";

import { NO_SCORE_COLOR, TIER_COLORS } from "../tiers";
import type { Bbox, Cluster, LatLong } from "../types";

setWorkerUrl(workerUrl);

// Free vector basemap, no key needed (checked 2026-11-25).
const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const FRANCE = { center: [2.5, 46.6] as [number, number], zoom: 5 };

export type ViewState = { bbox: Bbox; zoom: number; center: LatLong };

export type MapViewProps = {
  clusters: Cluster[];
  /** Vertices [long, lat] of the zone being drawn. */
  drawing?: [number, number][];
  onViewChange: (view: ViewState) => void;
  onMapClick?: (point: LatLong) => void;
  onProspectClick?: (prospectId: number) => void;
};

function clustersToGeojson(clusters: Cluster[]) {
  return {
    type: "FeatureCollection" as const,
    features: clusters.map((c) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [c.long, c.lat] },
      properties: { count: c.count, tier: c.tier ?? 0, prospect_id: c.prospect_id ?? 0 },
    })),
  };
}

function drawingToGeojson(points: [number, number][]) {
  const features: object[] = points.map((p) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: p },
    properties: {},
  }));
  if (points.length >= 2) {
    const ring = points.length >= 3 ? [...points, points[0]] : points;
    features.push({ type: "Feature", geometry: { type: "LineString", coordinates: ring }, properties: {} });
  }
  return { type: "FeatureCollection", features };
}

function viewOf(map: MapLibreMap): ViewState {
  const bounds = map.getBounds();
  const center = map.getCenter();
  return {
    bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
    zoom: map.getZoom(),
    center: { lat: center.lat, long: center.lng },
  };
}

export default function MapView({ clusters, drawing = [], onViewChange, onMapClick, onProspectClick }: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const ready = useRef(false);
  // Latest callbacks, read by the map handlers registered once.
  const callbacks = useRef({ onViewChange, onMapClick, onProspectClick });
  callbacks.current = { onViewChange, onMapClick, onProspectClick };
  const data = useRef({ clusters, drawing });
  data.current = { clusters, drawing };

  useEffect(() => {
    if (!container.current) return;
    const map = new MapLibreMap({ container: container.current, style: STYLE_URL, ...FRANCE });
    mapRef.current = map;

    map.on("load", () => {
      map.addSource("prospects", { type: "geojson", data: clustersToGeojson(data.current.clusters) });
      map.addLayer({
        id: "prospects-circles",
        type: "circle",
        source: "prospects",
        paint: {
          "circle-color": [
            "match",
            ["get", "tier"],
            ...TIER_COLORS.flatMap((color, index) => [index + 1, color]),
            NO_SCORE_COLOR,
          ] as never,
          "circle-radius": ["step", ["get", "count"], 7, 2, 12, 20, 16, 100, 22],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      map.addLayer({
        id: "prospects-counts",
        type: "symbol",
        source: "prospects",
        filter: [">", ["get", "count"], 1],
        layout: { "text-field": ["to-string", ["get", "count"]], "text-size": 12 },
        paint: { "text-color": "#ffffff" },
      });
      map.addSource("drawing", { type: "geojson", data: drawingToGeojson(data.current.drawing) as never });
      map.addLayer({ id: "drawing-line", type: "line", source: "drawing", paint: { "line-color": "#1d3557", "line-width": 2 } });
      map.addLayer({
        id: "drawing-points",
        type: "circle",
        source: "drawing",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 4, "circle-color": "#1d3557" },
      });
      ready.current = true;
      callbacks.current.onViewChange(viewOf(map));
    });

    map.on("moveend", () => callbacks.current.onViewChange(viewOf(map)));

    map.on("click", (event) => {
      const hit = ready.current
        ? map.queryRenderedFeatures(event.point, { layers: ["prospects-circles"] })[0]
        : undefined;
      if (!hit) {
        callbacks.current.onMapClick?.({ lat: event.lngLat.lat, long: event.lngLat.lng });
      }
    });

    map.on("click", "prospects-circles", (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const prospectId = Number(feature.properties?.prospect_id);
      if (prospectId) {
        callbacks.current.onProspectClick?.(prospectId);
      } else {
        map.easeTo({ center: event.lngLat, zoom: map.getZoom() + 2 });
      }
    });
    map.on("mouseenter", "prospects-circles", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "prospects-circles", () => (map.getCanvas().style.cursor = ""));

    return () => {
      ready.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready.current) return;
    (mapRef.current?.getSource("prospects") as GeoJSONSource | undefined)?.setData(clustersToGeojson(clusters));
  }, [clusters]);

  useEffect(() => {
    if (!ready.current) return;
    (mapRef.current?.getSource("drawing") as GeoJSONSource | undefined)?.setData(drawingToGeojson(drawing) as never);
  }, [drawing]);

  return <div ref={container} className="map" aria-label="Carte des prospects" />;
}

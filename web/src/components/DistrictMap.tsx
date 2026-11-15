"use client";

// Plain SVG — no map library. Projects lon/lat straight onto a flat plane
// with a cheap cos(latitude) correction for aspect ratio, not a real map
// projection; good enough for a small reference shape. All geometries
// passed to StateDistrictMap share ONE projection (computed from their
// combined bounding box) so the state outline and every district line up
// correctly instead of each being independently centered.
//
// Handles the one real edge case that would otherwise silently break it —
// Alaska's at-large district crosses the antimeridian (longitude jumps
// from ~+180 to ~-180) — by unwrapping negative longitudes when the raw
// span looks implausibly wide.

import { useRef, useState } from "react";

type Ring = [number, number][];
export type DistrictGeometry =
  | { type: "Polygon"; coordinates: Ring[] }
  | { type: "MultiPolygon"; coordinates: Ring[][] };

function allRings(geometry: DistrictGeometry): Ring[] {
  return geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
}

function buildProjection(geometries: DistrictGeometry[], size: number, padding: number) {
  const points = geometries.flatMap(allRings).flat();
  const rawLons = points.map((p) => p[0]);
  const crossesAntimeridian = Math.max(...rawLons) - Math.min(...rawLons) > 180;
  const unwrap = (lon: number) => (crossesAntimeridian && lon < 0 ? lon + 360 : lon);

  const lons = points.map((p) => unwrap(p[0]));
  const lats = points.map((p) => p[1]);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const lonScale = Math.cos(((minLat + maxLat) / 2) * (Math.PI / 180)) || 1;

  const spanX = (maxLon - minLon) * lonScale || 1;
  const spanY = maxLat - minLat || 1;
  const scale = Math.min((size - padding * 2) / spanX, (size - padding * 2) / spanY);
  const offsetX = (size - spanX * scale) / 2;
  const offsetY = (size - spanY * scale) / 2;

  return (lon: number, lat: number): [number, number] => {
    const x = offsetX + (unwrap(lon) - minLon) * lonScale * scale;
    const y = offsetY + (maxLat - lat) * scale;
    return [x, y];
  };
}

function pathFor(geometry: DistrictGeometry, project: (lon: number, lat: number) => [number, number]) {
  const rings = allRings(geometry);
  if (rings.length === 0) return "";
  return rings
    .map((ring) => `M${ring.map(([lon, lat]) => project(lon, lat).map((n) => n.toFixed(1)).join(",")).join("L")}Z`)
    .join(" ");
}

type DistrictEntry = { id: string; geometry: DistrictGeometry };

export default function StateDistrictMap({
  stateGeometry,
  districts,
  highlightId,
  size = 220,
  label,
}: {
  stateGeometry: DistrictGeometry;
  districts: DistrictEntry[];
  highlightId?: string;
  size?: number;
  label?: string;
}) {
  const padding = 6;
  const project = buildProjection([stateGeometry, ...districts.map((d) => d.geometry)], size, padding);
  const statePath = pathFor(stateGeometry, project);

  const [view, setView] = useState({ x: 0, y: 0, w: size, h: size });
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const zoomed = view.w !== size || view.x !== 0 || view.y !== 0;

  function zoomBy(factor: number, centerX: number, centerY: number) {
    setView((v) => {
      const newW = Math.min(size, Math.max(size * 0.12, v.w * factor));
      const ratioX = (centerX - v.x) / v.w;
      const ratioY = (centerY - v.y) / v.h;
      const newX = Math.min(size - newW, Math.max(0, centerX - ratioX * newW));
      const newY = Math.min(size - newW, Math.max(0, centerY - ratioY * newW));
      return { x: newX, y: newY, w: newW, h: newW };
    });
  }

  function handleWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    const px = view.x + ((e.clientX - rect.left) / rect.width) * view.w;
    const py = view.y + ((e.clientY - rect.top) / rect.height) * view.h;
    zoomBy(e.deltaY > 0 ? 1.15 : 0.87, px, py);
  }

  function handlePointerDown(e: React.PointerEvent<SVGSVGElement>) {
    dragRef.current = { x: e.clientX, y: e.clientY, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function handlePointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!dragRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = ((e.clientX - dragRef.current.x) / rect.width) * view.w;
    const dy = ((e.clientY - dragRef.current.y) / rect.height) * view.h;
    dragRef.current = { x: e.clientX, y: e.clientY, moved: true };
    setView((v) => ({
      ...v,
      x: Math.min(size - v.w, Math.max(0, v.x - dx)),
      y: Math.min(size - v.h, Math.max(0, v.y - dy)),
    }));
  }
  function endDrag() {
    dragRef.current = null;
  }
  function reset() {
    setView({ x: 0, y: 0, w: size, h: size });
  }

  if (!statePath) return null;

  return (
    <div className="district-map">
      <svg
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        width={size}
        height={size}
        role="img"
        aria-label={label}
        className="district-map__svg"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <path d={statePath} className="district-map__state" fillRule="evenodd" />
        {districts.map((d) => (
          <path
            key={d.id}
            d={pathFor(d.geometry, project)}
            fillRule="evenodd"
            className={`district-map__district${d.id === highlightId ? " district-map__district--active" : ""}`}
          />
        ))}
      </svg>
      <div className="district-map__controls">
        <button type="button" onClick={() => zoomBy(0.8, view.x + view.w / 2, view.y + view.h / 2)} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={() => zoomBy(1.25, view.x + view.w / 2, view.y + view.h / 2)} aria-label="Zoom out">
          −
        </button>
        {zoomed && (
          <button type="button" onClick={reset} aria-label="Reset view" className="district-map__reset">
            Reset
          </button>
        )}
      </div>
    </div>
  );
}

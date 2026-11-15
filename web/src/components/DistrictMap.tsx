// Plain server-renderable SVG — no map library, no client JS. Good enough
// for a small reference shape: project lon/lat straight onto a flat plane
// with a cheap cos(latitude) correction for aspect ratio, not a real map
// projection. Handles the one real edge case that would otherwise break —
// Alaska's at-large district crosses the antimeridian (its longitudes jump
// from ~+180 to ~-180), which would blow out the bounding box — by
// unwrapping negative longitudes when the raw span looks implausibly wide.

type Ring = [number, number][];
export type DistrictGeometry =
  | { type: "Polygon"; coordinates: Ring[] }
  | { type: "MultiPolygon"; coordinates: Ring[][] };

function allRings(geometry: DistrictGeometry): Ring[] {
  return geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
}

function buildPath(geometry: DistrictGeometry, width: number, height: number, padding: number) {
  const rings = allRings(geometry);
  const allPoints = rings.flat();
  if (allPoints.length === 0) return "";

  const rawLons = allPoints.map((p) => p[0]);
  const crossesAntimeridian = Math.max(...rawLons) - Math.min(...rawLons) > 180;
  const unwrap = (lon: number) => (crossesAntimeridian && lon < 0 ? lon + 360 : lon);

  const lons = allPoints.map((p) => unwrap(p[0]));
  const lats = allPoints.map((p) => p[1]);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const lonScale = Math.cos(((minLat + maxLat) / 2) * (Math.PI / 180)) || 1;

  const spanX = (maxLon - minLon) * lonScale || 1;
  const spanY = maxLat - minLat || 1;
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;

  const toXY = ([lon, lat]: [number, number]) => {
    const x = offsetX + (unwrap(lon) - minLon) * lonScale * scale;
    const y = offsetY + (maxLat - lat) * scale;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  return rings.map((ring) => `M${ring.map(toXY).join("L")}Z`).join(" ");
}

export default function DistrictMap({
  geometry,
  size = 160,
  label,
}: {
  geometry: DistrictGeometry;
  size?: number;
  label?: string;
}) {
  const path = buildPath(geometry, size, size, 6);
  if (!path) return null;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="district-map" role="img" aria-label={label}>
      <path d={path} fillRule="evenodd" className="district-map__shape" />
    </svg>
  );
}

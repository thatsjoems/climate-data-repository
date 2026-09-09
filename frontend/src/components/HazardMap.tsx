import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip } from 'react-leaflet'

export interface RegionMapPoint {
  region: string
  latitude: number
  longitude: number
  total_exposure_tzs: number
  record_count: number
  dominant_hazard: string
}

const HAZARD_COLORS: Record<string, string> = {
  Drought: '#C1600C',
  Flood: '#1F5C8B',
  Cyclone: '#7F3FA3',
  Landslide: '#6B4A2E',
  None: '#8A8677',
}

function formatTZS(n: number) {
  return new Intl.NumberFormat('en-TZ', { maximumFractionDigits: 0 }).format(n) + ' TZS'
}

// Area-proportional radius (sqrt scaling) so exposure differences read visually
// without the largest region overwhelming the whole map.
function radiusFor(exposure: number, maxExposure: number): number {
  if (maxExposure <= 0) return 10
  const minR = 8
  const maxR = 34
  return minR + (maxR - minR) * Math.sqrt(exposure / maxExposure)
}

export default function HazardMap({ points }: { points: RegionMapPoint[] }) {
  const maxExposure = points.reduce((max, p) => Math.max(max, p.total_exposure_tzs), 0)

  return (
    <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--color-border)' }}>
      <MapContainer
        center={[-6.37, 34.89]}
        zoom={5.4}
        style={{ height: '420px', width: '100%' }}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {points.map((p) => (
          <CircleMarker
            key={p.region}
            center={[p.latitude, p.longitude]}
            radius={radiusFor(p.total_exposure_tzs, maxExposure)}
            pathOptions={{
              color: HAZARD_COLORS[p.dominant_hazard] || HAZARD_COLORS.None,
              fillColor: HAZARD_COLORS[p.dominant_hazard] || HAZARD_COLORS.None,
              fillOpacity: 0.55,
              weight: 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -4]}>{p.region}</Tooltip>
            <Popup>
              <strong>{p.region}</strong><br />
              Dominant hazard: {p.dominant_hazard}<br />
              Loan exposure: {formatTZS(p.total_exposure_tzs)}<br />
              Records: {p.record_count}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}

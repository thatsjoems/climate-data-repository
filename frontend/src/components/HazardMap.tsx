import { useState } from 'react'
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

// PMO's public Tanzania Climate Vulnerability Maps tile service (tcvmp.pmo.go.tz),
// run jointly with the Global Center on Adaptation (GCA). This is a discovered
// public tile endpoint (found via browser network inspection), not a documented/
// contracted API - PMO could change or retire it without notice, so this layer
// is optional and fails gracefully (a broken tile just doesn't render; it never
// blocks our own institution-exposure markers, which come from our own data).
const PMO_INDICATORS: Record<string, string> = {
  Flood: 'flood',
  Drought: 'drought',
}

function pmoTileUrl(indicatorSlug: string): string {
  return `https://tcvmp.pmo.go.tz/tiles/singleband/climatology/${indicatorSlug}/ssp245/20202039/{z}/{x}/{y}.png?colormap=ylorrd`
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
  const [pmoIndicator, setPmoIndicator] = useState<string>('Flood')
  const [showPmoLayer, setShowPmoLayer] = useState(true)

  return (
    <div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
          <input type="checkbox" checked={showPmoLayer} onChange={(e) => setShowPmoLayer(e.target.checked)} />
          PMO hazard layer:
        </label>
        <select value={pmoIndicator} onChange={(e) => setPmoIndicator(e.target.value)} disabled={!showPmoLayer}>
          {Object.keys(PMO_INDICATORS).map((label) => (
            <option key={label} value={label}>{label}</option>
          ))}
        </select>
        <span style={{ color: 'var(--color-muted)' }}>(SSP245, 2020-2039 · source: PMO/GCA Tanzania Climate Vulnerability Maps)</span>
      </div>

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
          {showPmoLayer && (
            <TileLayer
              key={pmoIndicator}
              attribution={'Hazard layer: <a href="https://tcvmp.pmo.go.tz" target="_blank" rel="noreferrer">Prime Minister\'s Office / GCA - Tanzania Climate Vulnerability Maps</a>'}
              url={pmoTileUrl(PMO_INDICATORS[pmoIndicator])}
              opacity={0.55}
              // If PMO's endpoint is unreachable or the indicator slug is wrong, tiles
              // just fail to render - this must never break the map or our own markers.
              eventHandlers={{ tileerror: () => { /* silent - own markers below remain unaffected */ } }}
            />
          )}
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
                Dominant hazard (from submitted loan data): {p.dominant_hazard}<br />
                Loan exposure: {formatTZS(p.total_exposure_tzs)}<br />
                Records: {p.record_count}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <p style={{ fontSize: '0.72rem', color: 'var(--color-muted)', marginTop: '0.35rem' }}>
        The colored background (when enabled) is PMO's own published hazard index for the
        selected indicator/scenario/period - an independent public data source, not derived
        from institution submissions. Circles are this system's own institution-exposure data.
        The two are shown together for context; PMO's layer uses an unofficial public
        endpoint discovered via inspection, not a formal data-sharing agreement, so it may
        occasionally be unavailable.
      </p>
    </div>
  )
}

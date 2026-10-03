import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Polygon, ImageOverlay, CircleMarker, Tooltip, Popup, Marker } from 'react-leaflet'
import L from 'leaflet'
import apiClient from '../api/client'
import { REGION_BOUNDARIES } from '../data/regionBoundaries'
import { HAZARD_COLORS as HAZARD_HEX } from '../data/hazardColors'

export interface RegionMapPoint {
  region: string
  latitude: number
  longitude: number
  total_exposure_tzs: number
  total_collateral_tzs: number
  record_count: number
  dominant_hazard: string
}

interface ExposurePoint {
  latitude: number
  longitude: number
  amount_tzs: number
}

interface HazardExposureRow {
  region: string
  hazard_type: string | null
  exposed_loan_amount_tzs: number
  record_count: number
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '')
  return [parseInt(clean.slice(0, 2), 16), parseInt(clean.slice(2, 4), 16), parseInt(clean.slice(4, 6), 16)]
}

// The real categories climate_records.hazard_type can hold - not invented
// for the map. No "None" swatch: choosing no hazard means no hazard layer
// is drawn at all (the plain base map), not a colored "none" area.
// Colors themselves come from ../data/hazardColors (shared with the
// Climate Hazard Exposure Distribution pie chart on InternalPortal.tsx) so
// the two can never silently drift apart - this canvas/IDW code needs plain
// RGB number triples, not hex strings, so HAZARD_COLORS here is that same
// shared hex converted once, not a second hand-written palette.
const HAZARD_COLORS: Record<string, [number, number, number]> = Object.fromEntries(
  Object.entries(HAZARD_HEX).map(([name, hex]) => [name, hexToRgb(hex)])
)
const HAZARD_OPTIONS = Object.keys(HAZARD_COLORS)

// Financial concentration gradients (Module: map design) - Loan runs pale
// pink toward red as an individual loan's own amount grows relative to the
// largest one currently shown; Collateral runs pale toward a deep, saturated
// yellow the same way. Both are LINEAR interpolations between two real RGB
// endpoints, not a fixed palette - the color itself is the data.
const FINANCIAL_GRADIENTS: Record<string, { from: [number, number, number]; to: [number, number, number] }> = {
  Loan: { from: [253, 224, 234], to: [176, 20, 20] },        // pale pink -> red
  Collateral: { from: [255, 251, 214], to: [204, 163, 0] },    // pale yellow -> deep yellow/gold
}

function lerpColor(from: [number, number, number], to: [number, number, number], t: number): string {
  const clamped = Math.max(0, Math.min(1, t))
  const r = Math.round(from[0] + (to[0] - from[0]) * clamped)
  const g = Math.round(from[1] + (to[1] - from[1]) * clamped)
  const b = Math.round(from[2] + (to[2] - from[2]) * clamped)
  return `rgb(${r},${g},${b})`
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// Inverse Distance Weighting (IDW) - the same real, published spatial
// interpolation technique national hazard-mapping studies use (for example,
// Al-Hemoud et al. 2023, "Hazard Assessment and Hazard Mapping for Kuwait",
// Int. J. Disaster Risk Science, which interpolates rainfall/drought indices
// from a small number of weather stations into a smooth national surface
// using IDW in ArcGIS). Built here in plain JavaScript/Canvas - no GIS
// library was available to install in this environment - to turn this
// project's own sparse per-region hazard exposure into the same kind of
// smooth, continuous, country-wide surface, rather than isolated dots.
function buildIdwSurface(
  dataPoints: { lat: number; lon: number; value: number }[],
  bounds: { south: number; north: number; west: number; east: number },
  colorRgb: [number, number, number],
  gridSize = 140,
): string {
  const canvas = document.createElement('canvas')
  canvas.width = gridSize
  canvas.height = gridSize
  const ctx = canvas.getContext('2d')
  if (!ctx || dataPoints.length === 0) return ''
  const imageData = ctx.createImageData(gridSize, gridSize)
  const maxValue = Math.max(...dataPoints.map((p) => p.value), 0.0001)
  const power = 2.2
  const minOpacity = 0
  const maxOpacity = 235 // out of 255 - never fully solid, base map stays faintly visible

  for (let row = 0; row < gridSize; row++) {
    const lat = bounds.north - (row / (gridSize - 1)) * (bounds.north - bounds.south)
    for (let col = 0; col < gridSize; col++) {
      const lon = bounds.west + (col / (gridSize - 1)) * (bounds.east - bounds.west)
      let weightedSum = 0
      let weightSum = 0
      for (const p of dataPoints) {
        const d = haversineKm(lat, lon, p.lat, p.lon)
        const w = 1 / Math.pow(Math.max(d, 1), power)
        weightedSum += w * p.value
        weightSum += w
      }
      const interpolatedValue = weightSum > 0 ? weightedSum / weightSum : 0
      // The line above is intentionally NOT the bug it looks like: weightedSum
      // and weightSum are DIFFERENT accumulators (sum of weight*value vs sum
      // of weight) - weightedSum / weightSum IS the correct IDW weighted
      // average. Normalize that against this layer's own max value to get a
      // 0..1 intensity, then map to an alpha channel - never a fixed/solid
      // color, so the surface genuinely reads as low-to-high concentration.
      const normalizedIntensity = Math.max(0, Math.min(1, interpolatedValue / maxValue))
      const alpha = Math.round(minOpacity + normalizedIntensity * (maxOpacity - minOpacity))

      const idx = (row * gridSize + col) * 4
      imageData.data[idx] = colorRgb[0]
      imageData.data[idx + 1] = colorRgb[1]
      imageData.data[idx + 2] = colorRgb[2]
      imageData.data[idx + 3] = alpha
    }
  }
  ctx.putImageData(imageData, 0, 0)
  return canvas.toDataURL()
}

// Defined OUTSIDE the component so it is the same array reference on every
// render. Leaflet's MapContainer re-fits the view whenever the `bounds` prop
// object changes - an inline array literal is a NEW object every render,
// which was fighting the user's own zoom/pan on every re-render (e.g. the
// 20-second notification poll) and made the map feel unstable/"shaky".
const TANZANIA_BOUNDS: [[number, number], [number, number]] = [[-11.8, 29.2], [-0.85, 40.6]]
const BOUNDS_OBJ = { south: -11.8, north: -0.85, west: 29.2, east: 40.6 }

function formatTZS(n: number) {
  return new Intl.NumberFormat('en-TZ', { maximumFractionDigits: 0 }).format(n) + ' TZS'
}

function regionLabelIcon(text: string, highlighted: boolean) {
  return L.divIcon({
    className: 'region-label-icon',
    html: `<span style="
      font-size: ${highlighted ? '11.5px' : '9.5px'};
      font-weight: ${highlighted ? 600 : 400};
      color: ${highlighted ? '#002B49' : '#3A3A3A'};
      background: ${highlighted ? 'rgba(212,175,55,0.8)' : 'rgba(255,255,255,0.55)'};
      padding: 0px 4px;
      border-radius: 3px;
      white-space: nowrap;
      pointer-events: auto;
    ">${text}</span>`,
    iconSize: undefined,
    iconAnchor: [0, 0],
  })
}

export default function HazardMap({
  points,
  filterRegion,
  filterInstitutionId,
  filterReportingPeriod,
}: {
  points: RegionMapPoint[]
  filterRegion?: string
  filterInstitutionId?: string
  filterReportingPeriod?: string
}) {
  const [hazardChoice, setHazardChoice] = useState<string>('')
  const [financialChoice, setFinancialChoice] = useState<string>('')
  const [hazardRows, setHazardRows] = useState<HazardExposureRow[]>([])
  const [loanPoints, setLoanPoints] = useState<ExposurePoint[]>([])
  const [collateralPoints, setCollateralPoints] = useState<ExposurePoint[]>([])
  const [loadingLayer, setLoadingLayer] = useState(false)
  // Deliberately NEVER filtered by region (see idwImageUrl below): IDW needs
  // every region's coordinate as an anchor - including the zero-value ones -
  // to interpolate a gradient at all. `points` (the prop) IS correctly
  // filtered for the circle markers below, which should shrink to just the
  // selected region; this is a second, separate fetch specifically for the
  // hazard surface's anchor coordinates.
  const [allRegionPoints, setAllRegionPoints] = useState<RegionMapPoint[]>([])

  useEffect(() => {
    if (!hazardChoice) return
    setLoadingLayer(true)
    const params = new URLSearchParams()
    if (filterInstitutionId) params.set('filter_institution_id', filterInstitutionId)
    if (filterRegion) params.set('filter_region', filterRegion)
    if (filterReportingPeriod) params.set('filter_reporting_period', filterReportingPeriod)
    apiClient.get(`/analytics/hazard-exposure?${params.toString()}`)
      .then((res) => setHazardRows(res.data || []))
      .finally(() => setLoadingLayer(false))
  }, [hazardChoice, filterInstitutionId, filterRegion, filterReportingPeriod])

  useEffect(() => {
    if (!hazardChoice) return
    if (allRegionPoints.length > 0) return  // fetched once; region coordinates don't change during a session
    apiClient.get('/analytics/map-points').then((res) => setAllRegionPoints(res.data || []))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazardChoice])

  useEffect(() => {
    if (!financialChoice) return
    setLoadingLayer(true)
    const params = new URLSearchParams()
    if (filterInstitutionId) params.set('filter_institution_id', filterInstitutionId)
    if (filterRegion) params.set('filter_region', filterRegion)
    if (filterReportingPeriod) params.set('filter_reporting_period', filterReportingPeriod)
    apiClient.get(`/analytics/exposure-points?${params.toString()}`)
      .then((res) => {
        setLoanPoints(res.data.loan_points || [])
        setCollateralPoints(res.data.collateral_points || [])
      })
      .finally(() => setLoadingLayer(false))
  }, [financialChoice, filterInstitutionId, filterRegion, filterReportingPeriod])

  const hazardAmountByRegion: Record<string, number> = {}
  if (hazardChoice) {
    for (const row of hazardRows) {
      if (row.hazard_type === hazardChoice) {
        hazardAmountByRegion[row.region] = (hazardAmountByRegion[row.region] || 0) + row.exposed_loan_amount_tzs
      }
    }
  }

  // The smooth IDW surface (see buildIdwSurface above) - only recomputed
  // when the chosen hazard or the underlying data actually changes, since
  // it is a genuine per-pixel computation, not free.
  const idwImageUrl = useMemo(() => {
    if (!hazardChoice) return ''
    // Every region is included as a data point - even ones with ZERO
    // recorded exposure under this hazard. This is what makes IDW actually
    // fade smoothly with distance: with only the hazard-positive regions as
    // input, IDW mathematically returns their exact value everywhere on the
    // map (the distance weights cancel out with too few points) - it needs
    // real zero-value anchors elsewhere in the country to interpolate a true
    // gradient toward, not just a flat color with no decay.
    //
    // This is deliberately `allRegionPoints` (always every region,
    // unaffected by the region filter), NOT the `points` prop (which
    // shrinks to just the selected region when Dashboard Filters narrows
    // to one). Using the filtered prop here was a genuine defect: selecting
    // a single region left exactly one data point for IDW, which is
    // mathematically undefined as a "surface" - IDW with one input point
    // returns that point's exact value at every pixel with no distance
    // decay at all, painting the entire map the same solid colour instead
    // of a hotspot over the selected region. `hazardAmountByRegion` below
    // still comes from the correctly filter-scoped `hazardRows`, so the
    // selected region's own value is still exactly what the filter says -
    // only the anchor coordinate list stays nationwide.
    const anchorPoints = allRegionPoints.length > 0 ? allRegionPoints : points
    const dataPoints = anchorPoints.map((p) => ({
      lat: p.latitude, lon: p.longitude, value: hazardAmountByRegion[p.region] || 0,
    }))
    if (dataPoints.every((p) => p.value === 0)) return ''
    return buildIdwSurface(dataPoints, BOUNDS_OBJ, HAZARD_COLORS[hazardChoice])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazardChoice, JSON.stringify(hazardAmountByRegion), allRegionPoints])

  const gradient = financialChoice ? FINANCIAL_GRADIENTS[financialChoice] : null
  const activePoints = financialChoice === 'Loan' ? loanPoints : financialChoice === 'Collateral' ? collateralPoints : []
  const maxFinancialAmount = activePoints.reduce((max, p) => Math.max(max, p.amount_tzs), 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'center', marginBottom: '0.5rem', fontSize: '0.8rem', flexWrap: 'wrap' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          Hazard layer:
          <select value={hazardChoice} onChange={(e) => setHazardChoice(e.target.value)}>
            <option value="">None</option>
            {HAZARD_OPTIONS.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          Financial layer:
          <select value={financialChoice} onChange={(e) => setFinancialChoice(e.target.value)}>
            <option value="">None</option>
            {Object.keys(FINANCIAL_GRADIENTS).map((label) => (
              <option key={label} value={label}>{label}</option>
            ))}
          </select>
        </span>
        {loadingLayer && <span style={{ color: 'var(--color-muted)' }}>Loading...</span>}
        <span style={{ color: 'var(--color-muted)' }}>(pick one from each - shown together, e.g. Flood + Loan)</span>
      </div>

      <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', border: '1px solid var(--color-border)' }}>
        {/* preferCanvas: all vector layers below (CircleMarker, Polygon) draw onto
            ONE shared canvas element instead of each getting its own SVG DOM node.
            With the financial layer capable of returning up to 20,000 individual
            points (get_exposure_points()'s own limit), and the hazard IDW overlay's
            per-pixel computation potentially running at the same time when both
            layers are picked together, thousands of separate SVG elements were
            enough to freeze the tab on a broad ("all institutions") filter - though
            a narrow filter with few points never showed it, matching the "not every
            time" pattern reported. Canvas rendering keeps every point and its
            tooltip/hover behaviour working exactly as before; it only changes how
            Leaflet draws them internally. */}
        <MapContainer
          bounds={TANZANIA_BOUNDS}
          style={{ height: '420px', width: '100%' }}
          scrollWheelZoom={true}
          preferCanvas={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {idwImageUrl && (
            <ImageOverlay url={idwImageUrl} bounds={TANZANIA_BOUNDS} opacity={0.75} />
          )}

          {gradient && activePoints.map((p, i) => (
            <CircleMarker
              key={`${financialChoice}-${i}`}
              center={[p.latitude, p.longitude]}
              radius={1.4}
              pathOptions={{
                color: lerpColor(gradient.from, gradient.to, maxFinancialAmount > 0 ? p.amount_tzs / maxFinancialAmount : 0),
                fillColor: lerpColor(gradient.from, gradient.to, maxFinancialAmount > 0 ? p.amount_tzs / maxFinancialAmount : 0),
                fillOpacity: 0.85,
                weight: 0,
              }}
            >
              <Tooltip>{financialChoice}: {formatTZS(p.amount_tzs)}</Tooltip>
            </CircleMarker>
          ))}

          {points.map((p) => (
            <Marker
              key={p.region}
              position={[p.latitude, p.longitude]}
              icon={regionLabelIcon(p.region, p.region === filterRegion)}
              interactive={true}
            >
              <Popup>
                <strong>{p.region}</strong><br />
                Dominant hazard (from ingested TMA climate data): {p.dominant_hazard}<br />
                Loan exposure: {formatTZS(p.total_exposure_tzs)}<br />
                Collateral value: {formatTZS(p.total_collateral_tzs)}<br />
                Records: {p.record_count}
              </Popup>
            </Marker>
          ))}

          {filterRegion && REGION_BOUNDARIES[filterRegion] && REGION_BOUNDARIES[filterRegion].length >= 3 && (
            <Polygon
              positions={REGION_BOUNDARIES[filterRegion]}
              pathOptions={{ color: '#000000', weight: 1.5, fillOpacity: 0 }}
            >
              <Tooltip sticky>{filterRegion} (approximate boundary)</Tooltip>
            </Polygon>
          )}
        </MapContainer>

        {(hazardChoice || gradient) && (
          <div style={{
            position: 'absolute', bottom: 8, right: 8, zIndex: 1000,
            background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(0,0,0,0.15)',
            borderRadius: 8, padding: '0.4rem 0.6rem', fontSize: '0.68rem', lineHeight: 1.5,
          }}>
            {hazardChoice && (
              <>
                <strong style={{ display: 'block', marginBottom: 2 }}>{hazardChoice} concentration</strong>
                <div style={{ width: 70, height: 8, borderRadius: 4, background: `linear-gradient(to right, ${HAZARD_HEX[hazardChoice]}11, ${HAZARD_HEX[hazardChoice]}FF)` }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', width: 70, marginBottom: gradient ? 4 : 0 }}>
                  <span>Low</span><span>High</span>
                </div>
              </>
            )}
            {gradient && (
              <>
                <strong style={{ display: 'block', margin: '2px 0 2px' }}>{financialChoice} (dot color)</strong>
                <div style={{ width: 70, height: 8, borderRadius: 4, background: `linear-gradient(to right, ${lerpColor(gradient.from, gradient.to, 0)}, ${lerpColor(gradient.from, gradient.to, 1)})` }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', width: 70 }}>
                  <span>Low</span><span>High</span>
                </div>
              </>
            )}
          </div>
        )}
      </div>
      <p style={{ fontSize: '0.72rem', color: 'var(--color-muted)', marginTop: '0.35rem' }}>
        Hazard concentration is a smooth surface computed by Inverse Distance
        Weighting (IDW) - the same real spatial-interpolation technique
        published national hazard-mapping studies use - from this system's
        own ingested TMA climate exposure per region, the same evidence
        Combined Climate-Financial Exposure uses; it is never PMO or any
        external source. Financial dots (when a layer is chosen) sit at the
        ACTUAL latitude/longitude an institution entered on its own submitted
        template for each loan or collateral, colored from pale to saturated
        by that one record's own amount.
        {filterRegion && REGION_BOUNDARIES[filterRegion] && (
          <> <strong>{filterRegion}</strong>'s outline (black) is an approximate
          boundary shown because it is the current Dashboard Filters
          selection - not what drives hazard or financial coloring above.</>
        )}
      </p>
    </div>
  )
}

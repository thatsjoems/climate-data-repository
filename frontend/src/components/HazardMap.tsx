import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Polygon, ImageOverlay, CircleMarker, Tooltip, Popup, Marker } from 'react-leaflet'
import L from 'leaflet'
import apiClient from '../api/client'
import { REGION_BOUNDARIES } from '../data/regionBoundaries'
import { HAZARD_COLORS as HAZARD_HEX } from '../data/hazardColors'
import { hazardAmountsByRegion } from '../data/mapLayers'
import { buildIdwSurface } from './mapSurface'
import CheckboxDropdown from './CheckboxDropdown'

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

const FINANCIAL_OPTIONS = Object.keys(FINANCIAL_GRADIENTS)   // Loan, Collateral

function lerpColor(from: [number, number, number], to: [number, number, number], t: number): string {
  const clamped = Math.max(0, Math.min(1, t))
  const r = Math.round(from[0] + (to[0] - from[0]) * clamped)
  const g = Math.round(from[1] + (to[1] - from[1]) * clamped)
  const b = Math.round(from[2] + (to[2] - from[2]) * clamped)
  return `rgb(${r},${g},${b})`
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
  filterHazardType,
}: {
  points: RegionMapPoint[]
  filterRegion?: string
  filterInstitutionId?: string
  filterReportingPeriod?: string
  filterHazardType?: string
}) {
  // Both lists allow more than one choice at a time: [] = None, every layer = All. The lists change
  // these only when "Apply" is pressed (see CheckboxDropdown).
  const [hazardChoices, setHazardChoices] = useState<string[]>([])
  const [financialChoices, setFinancialChoices] = useState<string[]>([])
  const [hazardRows, setHazardRows] = useState<HazardExposureRow[]>([])
  const [loanPoints, setLoanPoints] = useState<ExposurePoint[]>([])
  const [collateralPoints, setCollateralPoints] = useState<ExposurePoint[]>([])
  const [loadingLayer, setLoadingLayer] = useState(false)
  // Deliberately NEVER filtered by region (see hazardSurfaces below): IDW needs
  // every region's coordinate as an anchor - including the zero-value ones -
  // to interpolate a gradient at all. `points` (the prop) IS correctly
  // filtered for the circle markers below, which should shrink to just the
  // selected region; this is a second, separate fetch specifically for the
  // hazard surface's anchor coordinates.
  const [allRegionPoints, setAllRegionPoints] = useState<RegionMapPoint[]>([])

  // One key for "which hazards / financial layers are chosen", so the effects below run when the choice changes,
  // not on every render (an array is a new object each time).
  const hazardKey = hazardChoices.join('|')
  const financialKey = financialChoices.join('|')

  // The hazard chosen in Dashboard Filters drives this map's hazard layer, so the two
  // controls cannot disagree: choosing Flood there draws the Flood layer here (and only it).
  // "None" (no hazard recorded) clears the layers. Clearing the filter leaves the analyst's own
  // choice of layers alone.
  useEffect(() => {
    if (!filterHazardType) return
    setHazardChoices(HAZARD_OPTIONS.includes(filterHazardType) ? [filterHazardType] : [])
  }, [filterHazardType])

  useEffect(() => {
    if (hazardChoices.length === 0) return
    setLoadingLayer(true)
    const params = new URLSearchParams()
    if (filterInstitutionId) params.set('filter_institution_id', filterInstitutionId)
    if (filterRegion) params.set('filter_region', filterRegion)
    if (filterReportingPeriod) params.set('filter_reporting_period', filterReportingPeriod)
    apiClient.get(`/analytics/hazard-exposure?${params.toString()}`)
      .then((res) => setHazardRows(res.data || []))
      .finally(() => setLoadingLayer(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazardKey, filterInstitutionId, filterRegion, filterReportingPeriod])

  useEffect(() => {
    if (hazardChoices.length === 0) return
    if (allRegionPoints.length > 0) return  // fetched once; region coordinates don't change during a session
    apiClient.get('/analytics/map-points').then((res) => setAllRegionPoints(res.data || []))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazardKey])

  useEffect(() => {
    if (financialChoices.length === 0) return
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [financialKey, filterInstitutionId, filterRegion, filterReportingPeriod])

  // One smooth IDW surface (see buildIdwSurface) for EACH chosen hazard, each in its own colour and scaled to
  // its own highest value - only recomputed when the choice or the underlying data actually changes, since it
  // is a genuine per-pixel computation, not free.
  const hazardSurfaces = useMemo(() => {
    if (hazardChoices.length === 0) return []
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
    // of a hotspot over the selected region. The amounts below still come
    // from the correctly filter-scoped `hazardRows`, so the selected
    // region's own value is still exactly what the filter says -
    // only the anchor coordinate list stays nationwide.
    const anchorPoints = allRegionPoints.length > 0 ? allRegionPoints : points
    const surfaces: { hazard: string; url: string }[] = []
    for (const hazard of hazardChoices) {
      const amounts = hazardAmountsByRegion(hazardRows, hazard)
      const dataPoints = anchorPoints.map((p) => ({ lat: p.latitude, lon: p.longitude, value: amounts[p.region] || 0 }))
      if (dataPoints.every((p) => p.value === 0)) continue
      const url = buildIdwSurface(dataPoints, BOUNDS_OBJ, HAZARD_COLORS[hazard])
      if (url) surfaces.push({ hazard, url })
    }
    return surfaces
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hazardKey, hazardRows, allRegionPoints, points])

  // Each chosen financial layer is drawn at the real coordinates entered on the template, in its own colour
  // scale (its own largest amount is its darkest dot).
  const financialLayers = FINANCIAL_OPTIONS.filter((label) => financialChoices.includes(label)).map((label) => {
    const pts = label === 'Loan' ? loanPoints : collateralPoints
    return {
      label, gradient: FINANCIAL_GRADIENTS[label], pts,
      max: pts.reduce((max, p) => Math.max(max, p.amount_tzs), 0),
    }
  })
  const hazardSwatches = Object.fromEntries(HAZARD_OPTIONS.map((h) => [h, HAZARD_HEX[h]]))
  const financialSwatches = Object.fromEntries(
    FINANCIAL_OPTIONS.map((label) => [label, lerpColor(FINANCIAL_GRADIENTS[label].from, FINANCIAL_GRADIENTS[label].to, 1)]),
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: '1.25rem', alignItems: 'center', marginBottom: '0.5rem', fontSize: '0.8rem', flexWrap: 'wrap' }}>
        <CheckboxDropdown
          label="Hazard layer"
          options={HAZARD_OPTIONS}
          selected={hazardChoices}
          onApply={setHazardChoices}
          swatches={hazardSwatches}
        />
        <CheckboxDropdown
          label="Financial layer"
          options={FINANCIAL_OPTIONS}
          selected={financialChoices}
          onApply={setFinancialChoices}
          swatches={financialSwatches}
        />
        {loadingLayer && <span style={{ color: 'var(--color-muted)' }}>Loading...</span>}
        <span style={{ color: 'var(--color-muted)' }}>(tick one or more boxes in each list, then press Apply - for example Flood + Drought with Loan + Collateral)</span>
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

          {hazardSurfaces.map((surface) => (
            <ImageOverlay key={surface.hazard} url={surface.url} bounds={TANZANIA_BOUNDS} opacity={0.75} />
          ))}

          {/* Collateral first, Loan on top of it, so a loan dot is never hidden under a collateral dot. */}
          {[...financialLayers].reverse().map((layer) =>
            layer.pts.map((p, i) => {
              const color = lerpColor(layer.gradient.from, layer.gradient.to, layer.max > 0 ? p.amount_tzs / layer.max : 0)
              return (
                <CircleMarker
                  key={`${layer.label}-${i}`}
                  center={[p.latitude, p.longitude]}
                  radius={1.4}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 0 }}
                >
                  <Tooltip>{layer.label}: {formatTZS(p.amount_tzs)}</Tooltip>
                </CircleMarker>
              )
            })
          )}

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

        {(hazardChoices.length > 0 || financialLayers.length > 0) && (
          <div
            data-testid="map-legend"
            style={{
              position: 'absolute', bottom: 8, right: 8, zIndex: 1000,
              background: 'rgba(255,255,255,0.92)', border: '1px solid rgba(0,0,0,0.15)',
              borderRadius: 8, padding: '0.4rem 0.6rem', fontSize: '0.68rem', lineHeight: 1.5,
              maxHeight: 300, overflowY: 'auto',
            }}
          >
            {hazardChoices.map((hazard) => {
              const hasSurface = hazardSurfaces.some((s) => s.hazard === hazard)
              return (
                <div key={hazard} style={{ marginBottom: 4 }}>
                  <strong style={{ display: 'block', marginBottom: 2 }}>
                    {hazard} concentration{!hasSurface && !loadingLayer ? ' (no exposure recorded)' : ''}
                  </strong>
                  <div style={{ width: 70, height: 8, borderRadius: 4, background: `linear-gradient(to right, ${HAZARD_HEX[hazard]}11, ${HAZARD_HEX[hazard]}FF)` }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', width: 70 }}>
                    <span>Low</span><span>High</span>
                  </div>
                </div>
              )
            })}
            {financialLayers.map((layer) => (
              <div key={layer.label} style={{ marginBottom: 4 }}>
                <strong style={{ display: 'block', margin: '2px 0 2px' }}>{layer.label} (dot color)</strong>
                <div style={{ width: 70, height: 8, borderRadius: 4, background: `linear-gradient(to right, ${lerpColor(layer.gradient.from, layer.gradient.to, 0)}, ${lerpColor(layer.gradient.from, layer.gradient.to, 1)})` }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', width: 70 }}>
                  <span>Low</span><span>High</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <p style={{ fontSize: '0.72rem', color: 'var(--color-muted)', marginTop: '0.35rem' }}>
        Hazard concentration is a smooth surface computed by Inverse Distance
        Weighting (IDW) - the same real spatial-interpolation technique
        published national hazard-mapping studies use - from this system's
        own ingested TMA climate exposure per region, the same evidence
        Combined Climate-Financial Exposure uses; it is never PMO or any
        external source. Each ticked hazard has its own surface and colour.
        Financial dots (for each ticked financial layer: Loan, Collateral or both) sit at the
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

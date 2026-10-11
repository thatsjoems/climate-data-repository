import { useMemo, useState } from 'react'
import { NO_READING_COLOR, SEVERITY_COLOR, SEVERITY_LABEL, SEVERITY_ORDER, severityKey } from './hazardSeverity'

/**
 * The district map of the Hazard Summary (Concept Note, Figure 3): every district of Tanzania, coloured by the highest
 * severity recorded there for the chosen hazard. It is drawn as plain SVG from the outlines of GET /analytics/district-shapes,
 * with no map tiles: nothing is requested from an outside service, so it works on a closed network, and it is not a street map.
 * A district that is not coloured has no reading in the selection, which is different from "safe". The table beside it carries
 * the same facts for anyone who cannot use the map.
 */

export interface DistrictShape {
  key: string
  region: string
  district: string
  rings: number[][][]      // each ring: [longitude, latitude] points
  borders?: number[][][]   // lines of the district's outer limit, drawn over the fills
}

export interface MapDistrict {
  region: string
  district: string
  readings: number
  highest_severity: string | null
  map_key?: string | null
}

const WIDTH = 1000
const RANK: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 }

/** True for a list that really holds outlines (a wrong answer from the server, or none, must not break the page). */
export function validShapes(value: unknown): value is DistrictShape[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((s) => s && typeof s.key === 'string' && Array.isArray(s.rings) && s.rings.length > 0)
  )
}

function layoutOf(shapes: DistrictShape[]) {
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity
  for (const s of shapes) {
    for (const ring of s.rings) {
      for (const [lon, lat] of ring) {
        if (lon < minLon) minLon = lon
        if (lon > maxLon) maxLon = lon
        if (lat < minLat) minLat = lat
        if (lat > maxLat) maxLat = lat
      }
    }
  }
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180)      // a degree of longitude is shorter away from the equator
  const scale = WIDTH / ((maxLon - minLon) * k)
  const height = Math.max(1, Math.round((maxLat - minLat) * scale))
  const paths = shapes.map((s) => ({
    key: s.key,
    region: s.region,
    district: s.district,
    d: s.rings
      .map((ring) => ring.map(([lon, lat], i) => `${i === 0 ? 'M' : 'L'}${((lon - minLon) * k * scale).toFixed(1)},${((maxLat - lat) * scale).toFixed(1)}`).join('') + 'Z')
      .join(''),
  }))
  const toPath = (line: number[][]) =>
    line.map(([lon, lat], i) => `${i === 0 ? 'M' : 'L'}${((lon - minLon) * k * scale).toFixed(1)},${((maxLat - lat) * scale).toFixed(1)}`).join('')
  const borders = shapes.map((s) => (s.borders || []).map(toPath).join('')).join('')
  return { height, paths, borders }
}

export default function DistrictMap({ shapes, districts, hazard }: { shapes: DistrictShape[]; districts: MapDistrict[]; hazard: string }) {
  const layout = useMemo(() => layoutOf(shapes), [shapes])

  // Readings may spell one district two ways; both land on one outline, so their figures are added up there.
  const byKey = useMemo(() => {
    const map = new Map<string, { readings: number; severity: string | null }>()
    for (const d of districts) {
      if (!d.map_key) continue
      const have = map.get(d.map_key)
      const worse = !have || (RANK[d.highest_severity || ''] || 0) > (RANK[have.severity || ''] || 0) ? d.highest_severity : have.severity
      map.set(d.map_key, { readings: (have ? have.readings : 0) + d.readings, severity: worse })
    }
    return map
  }, [districts])

  const [hovered, setHovered] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string | null>(null)       // a touch or a click keeps a district chosen
  const chosen = hovered ?? pinned

  function describe(key: string, region: string, district: string): string {
    const found = byKey.get(key)
    if (!found) return `${district}, ${region}: no ${hazard} reading in this selection`
    const grade = SEVERITY_LABEL[severityKey(found.severity)]
    return `${district}, ${region}: highest severity ${grade}, ${found.readings} reading${found.readings === 1 ? '' : 's'}`
  }

  const chosenPath = chosen ? layout.paths.find((p) => p.key === chosen) : undefined

  return (
    <div style={{ display: 'flex', gap: '1.2rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
      <svg
        viewBox={`0 0 ${WIDTH} ${layout.height}`}
        role="img"
        aria-label={`Map of the districts of Tanzania coloured by the highest ${hazard} severity recorded. The table below lists the same districts.`}
        style={{ width: '100%', maxWidth: '520px', height: 'auto', flex: '1 1 320px', background: '#FFFFFF', borderRadius: '6px' }}
        data-testid="district-map"
      >
        {layout.paths.map((p) => {
          const found = byKey.get(p.key)
          const fill = found ? SEVERITY_COLOR[severityKey(found.severity)] : NO_READING_COLOR
          return (
            <path
              key={p.key}
              d={p.d}
              fill={fill}
              stroke={fill}
              strokeWidth={0.6}
              opacity={chosen && chosen !== p.key ? 0.35 : 1}
              data-district={p.key}
              data-graded={found ? severityKey(found.severity) : 'NONE'}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHovered(p.key)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => setPinned(pinned === p.key ? null : p.key)}
            >
              <title>{describe(p.key, p.region, p.district)}</title>
            </path>
          )
        })}
        {layout.borders && (
          <path d={layout.borders} fill="none" stroke="#FFFFFF" strokeWidth={0.9} strokeLinejoin="round" pointerEvents="none" data-testid="district-borders" />
        )}
      </svg>

      <div style={{ flex: '1 1 200px', minWidth: '180px', fontSize: '0.82rem' }}>
        <div className="pie-legend" style={{ marginBottom: '0.8rem' }}>
          {SEVERITY_ORDER.map((k) => (
            <div className="pie-legend-item" key={k} style={{ display: 'flex' }}>
              <span className="pie-legend-swatch" style={{ background: SEVERITY_COLOR[k] }} />
              <span>{SEVERITY_LABEL[k]}</span>
            </div>
          ))}
          <div className="pie-legend-item" style={{ display: 'flex' }}>
            <span className="pie-legend-swatch" style={{ background: NO_READING_COLOR, border: '1px solid #CBD5E1' }} />
            <span>No {hazard} reading in this selection</span>
          </div>
        </div>
        <p aria-live="polite" style={{ margin: 0, minHeight: '2.6em' }} data-testid="district-map-readout">
          {chosenPath
            ? describe(chosenPath.key, chosenPath.region, chosenPath.district)
            : 'Point at a district, or touch it, to see its figures.'}
        </p>
      </div>
    </div>
  )
}

import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DistrictMap, { DistrictShape, MapDistrict, validShapes } from './DistrictMap'
import { NO_READING_COLOR, SEVERITY_COLOR } from './hazardSeverity'

function square(key: string, region: string, district: string, lon: number, lat: number): DistrictShape {
  return { key, region, district, rings: [[[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1], [lon, lat]]] }
}

const SHAPES: DistrictShape[] = [
  square('dodoma|bahi', 'Dodoma', 'Bahi', 35, -7),
  square('dodoma|chamwino', 'Dodoma', 'Chamwino', 36, -7),
  square('singida|ikungi', 'Singida', 'Ikungi', 35, -6),
  square('singida|manyoni', 'Singida', 'Manyoni', 36, -6),
]

const READINGS: MapDistrict[] = [
  { region: 'Dodoma', district: 'Bahi', readings: 2, highest_severity: 'HIGH', map_key: 'dodoma|bahi' },
  { region: 'Dodoma', district: 'Chamwino', readings: 1, highest_severity: 'LOW', map_key: 'dodoma|chamwino' },
  { region: 'Singida', district: 'Ikungi', readings: 1, highest_severity: null, map_key: 'singida|ikungi' },
]

function path(key: string): SVGPathElement {
  return document.querySelector(`[data-district="${key}"]`) as SVGPathElement
}

describe('DistrictMap', () => {
  it('draws the district borders over the fills, without catching the pointer, and copes with shapes that have none', () => {
    const withBorders = SHAPES.map((x) => ({ ...x, borders: [x.rings[0]] }))
    const { unmount } = render(<DistrictMap shapes={withBorders} districts={READINGS} hazard="Drought" />)
    const lines = document.querySelector('[data-testid="district-borders"]') as SVGPathElement
    expect(lines).not.toBeNull()
    expect(lines.getAttribute('pointer-events')).toBe('none')
    expect(lines.getAttribute('stroke')).toBe('#FFFFFF')
    const svg = document.querySelector('[data-testid="district-map"]') as SVGElement
    expect(svg.lastElementChild).toBe(lines)                       // above every fill
    unmount()
    render(<DistrictMap shapes={SHAPES} districts={READINGS} hazard="Drought" />)
    expect(document.querySelector('[data-testid="district-borders"]')).toBeNull()
  })

  it('draws every district and colours it by the highest severity recorded there', () => {
    render(<DistrictMap shapes={SHAPES} districts={READINGS} hazard="Drought" />)
    expect(document.querySelectorAll('[data-district]')).toHaveLength(4)
    expect(path('dodoma|bahi').getAttribute('fill')).toBe(SEVERITY_COLOR.HIGH)
    expect(path('dodoma|chamwino').getAttribute('fill')).toBe(SEVERITY_COLOR.LOW)
    expect(path('singida|ikungi').getAttribute('fill')).toBe(SEVERITY_COLOR.NOT_GRADED)   // recorded but not graded
    expect(path('singida|manyoni').getAttribute('fill')).toBe(NO_READING_COLOR)            // no reading at all
    expect(path('singida|manyoni').getAttribute('data-graded')).toBe('NONE')
  })

  it('says in its legend that an uncoloured district has no reading, not that it is safe', () => {
    render(<DistrictMap shapes={SHAPES} districts={READINGS} hazard="Flood" />)
    expect(screen.getByText('No Flood reading in this selection')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', expect.stringContaining('Flood'))
  })

  it('shows the figures of the district pointed at or touched, and a district with no reading says so', () => {
    render(<DistrictMap shapes={SHAPES} districts={READINGS} hazard="Drought" />)
    const readout = screen.getByTestId('district-map-readout')
    expect(readout).toHaveTextContent('Point at a district')
    fireEvent.mouseEnter(path('dodoma|bahi'))
    expect(readout).toHaveTextContent('Bahi, Dodoma: highest severity High, 2 readings')
    fireEvent.mouseLeave(path('dodoma|bahi'))
    fireEvent.click(path('singida|manyoni'))                       // a touch keeps it chosen
    expect(readout).toHaveTextContent('Manyoni, Singida: no Drought reading in this selection')
    fireEvent.click(path('singida|manyoni'))                       // and again lets it go
    expect(readout).toHaveTextContent('Point at a district')
  })

  it('adds up two spellings of one district and keeps the worse severity', () => {
    const twice: MapDistrict[] = [
      { region: 'Dodoma', district: 'Bahi', readings: 1, highest_severity: 'LOW', map_key: 'dodoma|bahi' },
      { region: 'Dodoma', district: 'bahi ', readings: 3, highest_severity: 'MEDIUM', map_key: 'dodoma|bahi' },
    ]
    render(<DistrictMap shapes={SHAPES} districts={twice} hazard="Drought" />)
    expect(path('dodoma|bahi').getAttribute('fill')).toBe(SEVERITY_COLOR.MEDIUM)
    fireEvent.mouseEnter(path('dodoma|bahi'))
    expect(screen.getByTestId('district-map-readout')).toHaveTextContent('Medium, 4 readings')
  })

  it('leaves a district the map has no outline for out of the picture without failing', () => {
    const odd: MapDistrict[] = [{ region: 'Dodoma', district: 'Atlantis', readings: 1, highest_severity: 'HIGH', map_key: null }]
    render(<DistrictMap shapes={SHAPES} districts={odd} hazard="Drought" />)
    expect(Array.from(document.querySelectorAll('[data-graded]')).every((p) => p.getAttribute('data-graded') === 'NONE')).toBe(true)
  })
})

describe('validShapes', () => {
  it('accepts a real list and refuses anything else, so a wrong answer cannot break the page', () => {
    expect(validShapes(SHAPES)).toBe(true)
    expect(validShapes([])).toBe(false)
    expect(validShapes(undefined)).toBe(false)
    expect(validShapes(null)).toBe(false)
    expect(validShapes('nope')).toBe(false)
    expect(validShapes([{ key: 'a', rings: [] }])).toBe(false)
    expect(validShapes([{ region: 'Dodoma', district: 'Bahi', readings: 1 }])).toBe(false)
  })
})

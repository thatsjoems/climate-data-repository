import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import HazardMap, { RegionMapPoint } from './HazardMap'
import apiClient from '../api/client'

// Leaflet needs a real browser to draw, so the map pieces are replaced by plain elements that record what the page asks
// them to draw: one element per hazard surface and one per financial dot. What is tested is WHICH layers the choices produce.
vi.mock('react-leaflet', async () => {
  const React = await import('react')
  const h = React.createElement
  return {
    MapContainer: ({ children }: any) => h('div', { 'data-testid': 'map' }, children),
    TileLayer: () => null,
    Polygon: () => null,
    Marker: () => null,
    Popup: () => null,
    ImageOverlay: ({ url }: any) => h('div', { 'data-testid': 'hazard-surface', 'data-url': url }),
    CircleMarker: ({ children }: any) => h('div', { 'data-testid': 'dot' }, children),
    Tooltip: ({ children }: any) => h('span', null, children),
  }
})

// A canvas does not exist here: the surface "image" is just a label naming the hazard colour it was built for.
vi.mock('./mapSurface', () => ({
  buildIdwSurface: (_points: unknown, _bounds: unknown, color: number[]) => `surface-${color.join('-')}`,
}))

const POINTS: RegionMapPoint[] = [
  { region: 'Dodoma', latitude: -6.16, longitude: 35.75, total_exposure_tzs: 1, total_collateral_tzs: 1, record_count: 1, dominant_hazard: 'Flood' },
  { region: 'Mwanza', latitude: -2.52, longitude: 32.9, total_exposure_tzs: 1, total_collateral_tzs: 1, record_count: 1, dominant_hazard: 'Drought' },
]

function mockApi() {
  return vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
    if (url.startsWith('/analytics/hazard-exposure')) {
      return { data: [
        { region: 'Dodoma', hazard_type: 'Flood', exposed_loan_amount_tzs: 100, record_count: 1 },
        { region: 'Mwanza', hazard_type: 'Drought', exposed_loan_amount_tzs: 70, record_count: 1 },
      ] } as any
    }
    if (url.startsWith('/analytics/map-points')) return { data: POINTS } as any
    if (url.startsWith('/analytics/exposure-points')) {
      return { data: {
        loan_points: [{ latitude: -6.1, longitude: 35.7, amount_tzs: 500 }],
        collateral_points: [{ latitude: -2.5, longitude: 32.9, amount_tzs: 800 }, { latitude: -3.3, longitude: 36.6, amount_tzs: 300 }],
      } } as any
    }
    return { data: [] } as any
  })
}

function applyChoice(listLabel: string, options: string[]) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(listLabel) }))
  const panel = within(screen.getByRole('group', { name: `${listLabel} options` }))
  for (const name of options) fireEvent.click(panel.getByRole('checkbox', { name }))
  fireEvent.click(panel.getByRole('button', { name: 'Apply' }))
}

describe('HazardMap layer choices', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('draws nothing until a layer is chosen', () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    expect(screen.queryAllByTestId('hazard-surface')).toHaveLength(0)
    expect(screen.queryAllByTestId('dot')).toHaveLength(0)
  })

  it('draws a surface for each of the hazards chosen together, not only one', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Hazard layer', ['Flood', 'Drought'])
    await waitFor(() => expect(screen.getAllByTestId('hazard-surface')).toHaveLength(2))
    const urls = screen.getAllByTestId('hazard-surface').map((e) => e.getAttribute('data-url'))
    expect(new Set(urls).size).toBe(2)              // each hazard has its own colour
    expect(screen.getByTestId('map-legend')).toHaveTextContent('Flood concentration')
    expect(screen.getByTestId('map-legend')).toHaveTextContent('Drought concentration')
  })

  it('All draws every hazard that has data and says so for the one that has none', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Hazard layer', ['All'])
    await waitFor(() => expect(screen.getAllByTestId('hazard-surface')).toHaveLength(2))   // Landslide and Cyclone have no exposure rows
    await waitFor(() => expect(screen.getByTestId('map-legend')).toHaveTextContent('Landslide concentration (no exposure recorded)'))
  })

  it('nothing changes on the map before Apply is pressed', async () => {
    const get = mockApi()
    render(<HazardMap points={POINTS} />)
    fireEvent.click(screen.getByRole('button', { name: /Hazard layer/ }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Hazard layer options' })).getByRole('checkbox', { name: 'Flood' }))
    expect(get).not.toHaveBeenCalled()
    expect(screen.queryAllByTestId('hazard-surface')).toHaveLength(0)
  })

  it('Financial All draws loan and collateral dots together at their own coordinates', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Financial layer', ['All'])
    await waitFor(() => expect(screen.getAllByTestId('dot')).toHaveLength(3))   // 1 loan + 2 collateral
    expect(screen.getAllByText(/^Loan:/)).toHaveLength(1)
    expect(screen.getAllByText(/^Collateral:/)).toHaveLength(2)
  })

  it('Loan alone, then Collateral alone, draws only that layer', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Financial layer', ['Loan'])
    await waitFor(() => expect(screen.getAllByTestId('dot')).toHaveLength(1))
    expect(screen.getByText(/^Loan:/)).toBeInTheDocument()

    applyChoice('Financial layer', ['Loan', 'Collateral'])   // untick Loan, tick Collateral
    await waitFor(() => expect(screen.getAllByTestId('dot')).toHaveLength(2))
    expect(screen.queryByText(/^Loan:/)).not.toBeInTheDocument()
  })

  it('None removes the layers again', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Financial layer', ['All'])
    await waitFor(() => expect(screen.getAllByTestId('dot')).toHaveLength(3))
    applyChoice('Financial layer', ['None'])
    await waitFor(() => expect(screen.queryAllByTestId('dot')).toHaveLength(0))
  })

  it('hazards and financial layers can be shown at the same time', async () => {
    mockApi()
    render(<HazardMap points={POINTS} />)
    applyChoice('Hazard layer', ['Flood', 'Drought'])
    applyChoice('Financial layer', ['All'])
    await waitFor(() => {
      expect(screen.getAllByTestId('hazard-surface')).toHaveLength(2)
      expect(screen.getAllByTestId('dot')).toHaveLength(3)
    })
  })

  it('the hazard picked in Dashboard Filters is drawn, and only that one', async () => {
    mockApi()
    render(<HazardMap points={POINTS} filterHazardType="Flood" />)
    await waitFor(() => expect(screen.getAllByTestId('hazard-surface')).toHaveLength(1))
    expect(screen.getByRole('button', { name: /Hazard layer: Flood/ })).toBeInTheDocument()
  })
})

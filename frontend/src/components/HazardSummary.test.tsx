import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import HazardSummary, { HazardSummaryData } from './HazardSummary'
import apiClient from '../api/client'

function summary(over: Partial<HazardSummaryData> = {}): HazardSummaryData {
  return {
    hazard_type: 'Drought', reporting_period: null, region: null, validated_only: true,
    districts_affected: 3, regions_affected: 2, readings: 5, readings_without_district: 0,
    highest_severity: 'HIGH',
    districts_by_severity: { HIGH: 1, MEDIUM: 1, LOW: 0, NOT_GRADED: 1 },
    districts: [
      { region: 'Dodoma', district: 'Bahi', readings: 2, highest_severity: 'HIGH' },
      { region: 'Dodoma', district: 'Chamwino', readings: 2, highest_severity: 'MEDIUM' },
      { region: 'Singida', district: 'Ikungi', readings: 1, highest_severity: null },
    ],
    available_periods: ['2026-Q2', '2026-Q1'],
    available_regions: ['Dodoma', 'Singida'],
    ...over,
  }
}

function lastUrl(get: { mock: { calls: unknown[][] } }): URL {
  const calls = get.mock.calls
  return new URL(String(calls[calls.length - 1][0]), 'http://x')
}

describe('HazardSummary', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('shows the figures and the districts worst first, and never claims a population', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary() } as any)
    render(<HazardSummary />)
    await waitFor(() => expect(screen.getByTestId('hs-districts')).toHaveTextContent('3'))
    expect(screen.getByTestId('hs-regions')).toHaveTextContent('2')
    expect(screen.getByTestId('hs-highest')).toHaveTextContent('High')
    expect(screen.getByTestId('hs-readings')).toHaveTextContent('5')
    const rows = screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)
    expect(rows).toEqual(['Bahi', 'Chamwino', 'Ikungi'])
    expect(screen.getByText(/number of people affected is not shown/i)).toBeInTheDocument()
    expect(screen.getAllByText('Not graded').length).toBeGreaterThan(0)
  })

  it('starts with Drought and asks the server again when the hazard changes', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary() } as any)
    render(<HazardSummary />)
    await waitFor(() => expect(get).toHaveBeenCalled())
    expect(lastUrl(get).pathname).toBe('/analytics/hazard-summary')
    expect(lastUrl(get).searchParams.get('filter_hazard_type')).toBe('Drought')
    fireEvent.change(screen.getByLabelText('Hazard type'), { target: { value: 'Flood' } })
    await waitFor(() => expect(lastUrl(get).searchParams.get('filter_hazard_type')).toBe('Flood'))
  })

  it('offers the periods and regions the server says have readings, and sends the choice', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary() } as any)
    render(<HazardSummary />)
    const period = await screen.findByLabelText('Time period')
    await waitFor(() => expect(within(period).getByRole('option', { name: '2026-Q2' })).toBeInTheDocument())
    expect(within(screen.getByLabelText('Region')).getByRole('option', { name: 'Singida' })).toBeInTheDocument()
    fireEvent.change(period, { target: { value: '2026-Q1' } })
    await waitFor(() => expect(lastUrl(get).searchParams.get('filter_reporting_period')).toBe('2026-Q1'))
    fireEvent.change(screen.getByLabelText('Region'), { target: { value: 'Dodoma' } })
    await waitFor(() => expect(lastUrl(get).searchParams.get('filter_region')).toBe('Dodoma'))
  })

  it('counts only validated readings until the box is ticked', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary() } as any)
    render(<HazardSummary />)
    await waitFor(() => expect(get).toHaveBeenCalled())
    expect(lastUrl(get).searchParams.get('validated_only')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox', { name: /not yet validated/i }))
    await waitFor(() => expect(lastUrl(get).searchParams.get('validated_only')).toBe('false'))
  })

  it('lists the worst ten districts and shows all of them on request', async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      region: 'Dodoma', district: `District ${String(i + 1).padStart(2, '0')}`, readings: 1, highest_severity: 'LOW',
    }))
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary({ districts: many, districts_affected: 12 }) } as any)
    render(<HazardSummary />)
    await screen.findByText('District 01')
    expect(screen.getAllByRole('row')).toHaveLength(11)              // header + 10
    expect(screen.queryByText('District 12')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 12 districts' }))
    expect(screen.getByText('District 12')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Show the worst 10 only/ }))
    expect(screen.queryByText('District 12')).not.toBeInTheDocument()
  })

  it('says so when readings exist for a region only', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: summary({ readings_without_district: 2 }) } as any)
    render(<HazardSummary />)
    expect(await screen.findByText(/2 of these readings were recorded for a region only/)).toBeInTheDocument()
  })

  it('says plainly that nothing is recorded, instead of showing zeros as good news', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: summary({ readings: 0, districts_affected: 0, regions_affected: 0, highest_severity: null, districts: [],
        districts_by_severity: { HIGH: 0, MEDIUM: 0, LOW: 0, NOT_GRADED: 0 }, available_periods: [], available_regions: [] }),
    } as any)
    render(<HazardSummary />)
    expect(await screen.findByText(/No Drought readings are recorded for this selection/)).toBeInTheDocument()
    expect(screen.queryByTestId('hs-districts')).not.toBeInTheDocument()
  })

  it('reports a failed load', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('network'))
    render(<HazardSummary />)
    expect(await screen.findByText('The hazard summary could not be loaded.')).toBeInTheDocument()
  })
})

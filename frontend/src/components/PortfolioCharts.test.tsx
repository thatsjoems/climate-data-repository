import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import PortfolioCharts, { compactNumber } from './PortfolioCharts'
import apiClient from '../api/client'

describe('compactNumber', () => {
  it('uses T, B, M and K like the dashboard mockup', () => {
    expect(compactNumber(55_660_000_000_000)).toBe('55.66 T')
    expect(compactNumber(8_420_000_000)).toBe('8.42 B')
    expect(compactNumber(2_500_000)).toBe('2.50 M')
    expect(compactNumber(1_500)).toBe('1.5 K')
    expect(compactNumber(12)).toBe('12')
  })
})

describe('PortfolioCharts', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('asks the server for each chart and drills from region to district on click', async () => {
    const get = vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      const groupBy = new URL(url, 'http://x').searchParams.get('group_by')
      const data = groupBy === 'region'
        ? [{ label: 'Mwanza', value: 4e9, record_count: 2, share_pct: 80 }, { label: 'Dodoma', value: 1e9, record_count: 1, share_pct: 20 }]
        : []
      return { data } as any
    })
    render(<PortfolioCharts filterQuery="filter_reporting_period=2026-Q1" />)
    const bar = await screen.findByText('Mwanza')
    expect(get).toHaveBeenCalled()
    expect(String(get.mock.calls[0][0])).toContain('filter_reporting_period=2026-Q1')
    fireEvent.click(bar)
    await waitFor(() => {
      const urls = get.mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.includes('group_by=district') && u.includes('filter_region=Mwanza'))).toBe(true)
    })
  })
})

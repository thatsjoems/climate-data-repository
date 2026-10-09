import { describe, it, expect } from 'vitest'
import { hazardAmountsByRegion, isChecked, summaryLabel, toggleOption } from './mapLayers'

const HAZARDS = ['Flood', 'Drought', 'Landslide', 'Cyclone']
const FINANCIAL = ['Loan', 'Collateral']

describe('toggleOption', () => {
  it('lets more than one hazard be chosen, always in the list order', () => {
    let sel: string[] = []
    sel = toggleOption(sel, 'Drought', HAZARDS)
    sel = toggleOption(sel, 'Flood', HAZARDS)
    expect(sel).toEqual(['Flood', 'Drought'])
  })

  it('unticking one layer leaves the others', () => {
    expect(toggleOption(['Flood', 'Drought', 'Cyclone'], 'Drought', HAZARDS)).toEqual(['Flood', 'Cyclone'])
  })

  it('All ticks every layer, and All again clears them', () => {
    const all = toggleOption([], 'All', HAZARDS)
    expect(all).toEqual(HAZARDS)
    expect(toggleOption(all, 'All', HAZARDS)).toEqual([])
  })

  it('All from a partial choice completes it', () => {
    expect(toggleOption(['Flood'], 'All', FINANCIAL)).toEqual(FINANCIAL)
  })

  it('None clears everything', () => {
    expect(toggleOption(['Loan', 'Collateral'], 'None', FINANCIAL)).toEqual([])
  })
})

describe('isChecked', () => {
  it('None is ticked only when nothing is', () => {
    expect(isChecked([], 'None', FINANCIAL)).toBe(true)
    expect(isChecked(['Loan'], 'None', FINANCIAL)).toBe(false)
  })

  it('All follows from every layer being ticked (Loan and Collateral)', () => {
    expect(isChecked(['Loan'], 'All', FINANCIAL)).toBe(false)
    expect(isChecked(['Loan', 'Collateral'], 'All', FINANCIAL)).toBe(true)
    expect(isChecked([], 'All', [])).toBe(false)
  })

  it('a layer is ticked when it is chosen', () => {
    expect(isChecked(['Flood'], 'Flood', HAZARDS)).toBe(true)
    expect(isChecked(['Flood'], 'Drought', HAZARDS)).toBe(false)
  })
})

describe('summaryLabel', () => {
  it('names what is shown on the closed list', () => {
    expect(summaryLabel([], HAZARDS)).toBe('None')
    expect(summaryLabel(['Flood', 'Drought'], HAZARDS)).toBe('Flood, Drought')
    expect(summaryLabel(HAZARDS, HAZARDS)).toBe('All')
    expect(summaryLabel(['Collateral'], FINANCIAL)).toBe('Collateral')
  })
})

describe('hazardAmountsByRegion', () => {
  const rows = [
    { region: 'Dodoma', hazard_type: 'Flood', exposed_loan_amount_tzs: 100 },
    { region: 'Dodoma', hazard_type: 'Flood', exposed_loan_amount_tzs: 50 },
    { region: 'Mwanza', hazard_type: 'Drought', exposed_loan_amount_tzs: 70 },
    { region: 'Arusha', hazard_type: null, exposed_loan_amount_tzs: 10 },
  ]

  it('adds up one hazard per region and ignores the others', () => {
    expect(hazardAmountsByRegion(rows, 'Flood')).toEqual({ Dodoma: 150 })
    expect(hazardAmountsByRegion(rows, 'Drought')).toEqual({ Mwanza: 70 })
    expect(hazardAmountsByRegion(rows, 'Cyclone')).toEqual({})
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import CheckboxDropdown from './CheckboxDropdown'

const HAZARDS = ['Flood', 'Drought', 'Landslide', 'Cyclone']

function open(label = 'Hazard layer') {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(label) }))
  return within(screen.getByRole('group', { name: `${label} options` }))
}

describe('CheckboxDropdown', () => {
  it('offers None, All and a tick box for each option', () => {
    render(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={[]} onApply={vi.fn()} />)
    const panel = open()
    for (const name of ['None', 'All', ...HAZARDS]) {
      expect(panel.getByRole('checkbox', { name })).toBeInTheDocument()
    }
    expect(panel.getByRole('checkbox', { name: 'None' })).toBeChecked()
    expect(panel.getByRole('checkbox', { name: 'Flood' })).not.toBeChecked()
  })

  it('applies two hazards chosen together', () => {
    const onApply = vi.fn()
    render(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={[]} onApply={onApply} />)
    const panel = open()
    fireEvent.click(panel.getByRole('checkbox', { name: 'Drought' }))
    fireEvent.click(panel.getByRole('checkbox', { name: 'Flood' }))
    expect(onApply).not.toHaveBeenCalled()          // nothing changes until Apply
    fireEvent.click(panel.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenCalledWith(['Flood', 'Drought'])
    expect(screen.queryByRole('group')).not.toBeInTheDocument()   // the list closes
  })

  it('All ticks every box and None clears them', () => {
    const onApply = vi.fn()
    render(<CheckboxDropdown label="Financial layer" options={['Loan', 'Collateral']} selected={[]} onApply={onApply} />)
    const panel = open('Financial layer')
    fireEvent.click(panel.getByRole('checkbox', { name: 'All' }))
    expect(panel.getByRole('checkbox', { name: 'Loan' })).toBeChecked()
    expect(panel.getByRole('checkbox', { name: 'Collateral' })).toBeChecked()
    fireEvent.click(panel.getByRole('checkbox', { name: 'None' }))
    expect(panel.getByRole('checkbox', { name: 'Loan' })).not.toBeChecked()
    expect(panel.getByRole('checkbox', { name: 'All' })).not.toBeChecked()
    fireEvent.click(panel.getByRole('checkbox', { name: 'Loan' }))
    fireEvent.click(panel.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenCalledWith(['Loan'])
  })

  it('shows All ticked once both financial layers are ticked one by one', () => {
    render(<CheckboxDropdown label="Financial layer" options={['Loan', 'Collateral']} selected={[]} onApply={vi.fn()} />)
    const panel = open('Financial layer')
    fireEvent.click(panel.getByRole('checkbox', { name: 'Loan' }))
    expect(panel.getByRole('checkbox', { name: 'All' })).not.toBeChecked()
    fireEvent.click(panel.getByRole('checkbox', { name: 'Collateral' }))
    expect(panel.getByRole('checkbox', { name: 'All' })).toBeChecked()
  })

  it('names the current choice on the closed list', () => {
    const { rerender } = render(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={[]} onApply={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Hazard layer: None/ })).toBeInTheDocument()
    rerender(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={['Flood', 'Drought']} onApply={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Hazard layer: Flood, Drought/ })).toBeInTheDocument()
    rerender(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={HAZARDS} onApply={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Hazard layer: All/ })).toBeInTheDocument()
  })

  it('closing without Apply keeps the previous choice, and reopening starts from it', () => {
    const onApply = vi.fn()
    render(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={['Flood']} onApply={onApply} />)
    let panel = open()
    fireEvent.click(panel.getByRole('checkbox', { name: 'Cyclone' }))
    fireEvent.mouseDown(document.body)                       // a click elsewhere closes it
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(onApply).not.toHaveBeenCalled()
    panel = open()
    expect(panel.getByRole('checkbox', { name: 'Flood' })).toBeChecked()
    expect(panel.getByRole('checkbox', { name: 'Cyclone' })).not.toBeChecked()
  })

  it('Escape closes the list without applying', () => {
    const onApply = vi.fn()
    render(<CheckboxDropdown label="Hazard layer" options={HAZARDS} selected={[]} onApply={onApply} />)
    const panel = open()
    fireEvent.click(panel.getByRole('checkbox', { name: 'Flood' }))
    fireEvent.keyDown(screen.getByRole('group'), { key: 'Escape' })
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(onApply).not.toHaveBeenCalled()
  })
})

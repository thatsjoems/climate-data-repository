import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useBusy } from './useBusy'

describe('useBusy', () => {
  it('marks an action busy at once and free again when it ends', async () => {
    const { result } = renderHook(() => useBusy())
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    let done: Promise<unknown> | undefined
    act(() => { done = result.current.run('save', () => gate) })
    expect(result.current.isBusy('save')).toBe(true)
    expect(result.current.isBusy('other')).toBe(false)
    await act(async () => { release(); await done })
    expect(result.current.isBusy('save')).toBe(false)
  })

  it('ignores a second click on the same action while the first is running', async () => {
    const { result } = renderHook(() => useBusy())
    let calls = 0
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    let first: Promise<unknown> | undefined
    act(() => {
      first = result.current.run('save', async () => { calls++; await gate })
      void result.current.run('save', async () => { calls++ })
    })
    expect(calls).toBe(1)
    await act(async () => { release(); await first })
  })

  it('is free again after a failure', async () => {
    const { result } = renderHook(() => useBusy())
    await act(async () => { await result.current.run('x', async () => { throw new Error('no') }).catch(() => undefined) })
    expect(result.current.isBusy('x')).toBe(false)
  })
})

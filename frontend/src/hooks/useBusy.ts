import { useCallback, useRef, useState } from 'react'

// One button, one action at a time. `run(key, fn)` starts `fn` unless an action with the same key is already running (a second
// click is ignored, so nothing is sent twice) and `isBusy(key)` tells the page to disable the button and say "Working..." AT ONCE,
// before the server has answered.
export function useBusy() {
  const running = useRef(new Set<string>())
  const [keys, setKeys] = useState<ReadonlySet<string>>(new Set())

  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>): Promise<T | undefined> => {
    if (running.current.has(key)) return undefined
    running.current.add(key)
    setKeys(new Set(running.current))
    try {
      return await fn()
    } finally {
      running.current.delete(key)
      setKeys(new Set(running.current))
    }
  }, [])

  const isBusy = useCallback((key: string) => keys.has(key), [keys])
  return { run, isBusy, anyBusy: keys.size > 0 }
}

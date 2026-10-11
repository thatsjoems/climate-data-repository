import { useEffect, useState } from 'react'
import { subscribePending, getPending } from '../api/client'

// A thin bar across the top of the page while the server is being asked for something. It appears at once (so a click is never
// met with silence) and only after 150 ms is it drawn, so quick answers do not make the page flicker.
export default function RequestProgress() {
  const [pending, setPending] = useState(getPending())
  const [visible, setVisible] = useState(false)
  useEffect(() => subscribePending(setPending), [])
  useEffect(() => {
    if (pending <= 0) { setVisible(false); return }
    const t = window.setTimeout(() => setVisible(true), 150)
    return () => window.clearTimeout(t)
  }, [pending])
  if (!visible) return null
  return <div className="request-progress" role="progressbar" aria-label="Working" aria-busy="true" />
}

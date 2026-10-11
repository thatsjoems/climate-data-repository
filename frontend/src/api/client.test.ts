import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios from 'axios'
import apiClient, { getPending, subscribePending, getAccessToken, hasSessionHint, refreshSession, setAccessToken, setSessionHint, WEB_CLIENT_HEADERS } from './client'

// The request interceptor is what makes every authenticated screen work at
// all - if it silently stopped attaching the access token, every request
// would look like an anonymous one to the backend. This is worth a direct
// test rather than only being exercised incidentally by other tests.
//
// axios types `interceptors.request.handlers` as possibly undefined (it
// guards against an interceptor having been ejected) - in practice it is
// always populated here, since client.ts registers this interceptor at
// module load, before any test runs. The optional chaining below satisfies
// TypeScript's strict checks; the thrown error backs up that guarantee at
// runtime so a genuine regression (the interceptor failing to register at
// all) fails loudly instead of silently passing.

function getRequestInterceptor() {
  const handler = apiClient.interceptors.request.handlers?.[0]
  if (!handler?.fulfilled) {
    throw new Error('Request interceptor was not registered - client.ts may have changed.')
  }
  return handler.fulfilled
}

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken(null)
  })

  it('attaches the access token, which is kept in memory, as a Bearer header', async () => {
    setAccessToken('abc123')
    const fulfilled = getRequestInterceptor()
    const config = await fulfilled({ headers: {} } as any)
    expect(config.headers.Authorization).toBe('Bearer abc123')
  })

  it('does not set an Authorization header when there is no token', async () => {
    const fulfilled = getRequestInterceptor()
    const config = await fulfilled({ headers: {} } as any)
    expect(config.headers.Authorization).toBeUndefined()
  })

  it('never takes a token from the browser storage, even one an older version left there', async () => {
    localStorage.setItem('cdr_token', 'old-token-in-storage')
    const fulfilled = getRequestInterceptor()
    const config = await fulfilled({ headers: {} } as any)
    expect(config.headers.Authorization).toBeUndefined()
  })

  it('sends the cookie with its requests (the refresh cookie is HttpOnly and only the browser can send it)', () => {
    expect(apiClient.defaults.withCredentials).toBe(true)
  })
})

describe('refreshSession', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken(null)
  })
  afterEach(() => vi.restoreAllMocks())

  it('asks the server with the cookie and the application header, with no token in the request, and keeps the new access token in memory only', async () => {
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'new-access', user: { id: 'u1', role: 'BOT_USER' } } })
    const session = await refreshSession()
    expect(session.access_token).toBe('new-access')
    expect(post).toHaveBeenCalledTimes(1)
    const [url, body, options] = post.mock.calls[0] as any[]
    expect(url).toMatch(/\/auth\/refresh$/)
    expect(body).toBeNull()                                          // no refresh token travels in the request: the cookie carries it
    expect(options.withCredentials).toBe(true)
    expect(options.headers).toEqual(WEB_CLIENT_HEADERS)
    expect(getAccessToken()).toBe('new-access')
    expect(Object.keys(localStorage)).toEqual([])                    // nothing was written to the browser storage
  })

  it('makes one call however many callers ask at the same moment', async () => {
    const post = vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'x', user: {} } })
    await Promise.all([refreshSession(), refreshSession(), refreshSession()])
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('fails when the server refuses, and leaves no token behind', async () => {
    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 401 } })
    await expect(refreshSession()).rejects.toBeTruthy()
    expect(getAccessToken()).toBeNull()
  })
})

describe('the session hint', () => {
  beforeEach(() => localStorage.clear())

  it('is only a yes/no flag, and can be switched on and off', () => {
    expect(hasSessionHint()).toBe(false)
    setSessionHint(true)
    expect(hasSessionHint()).toBe(true)
    expect(localStorage.getItem('cdr_session')).toBe('1')            // not a token
    setSessionHint(false)
    expect(hasSessionHint()).toBe(false)
  })
})

describe('leftovers of the older way of keeping tokens', () => {
  it('are removed from the browser when the application starts', async () => {
    localStorage.setItem('cdr_token', 'a')
    localStorage.setItem('cdr_refresh_token', 'b')
    localStorage.setItem('cdr_user', '{}')
    vi.resetModules()
    await import('./client')
    expect(localStorage.getItem('cdr_token')).toBeNull()
    expect(localStorage.getItem('cdr_refresh_token')).toBeNull()
    expect(localStorage.getItem('cdr_user')).toBeNull()
  })
})

describe('the count of requests waiting for the server (drives the progress bar)', () => {
  it('rises while a request is out and falls when it is answered, or fails', async () => {
    const seen: number[] = []
    const stop = subscribePending((n) => seen.push(n))
    expect(getPending()).toBe(0)
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const ok = (config: any) => gate.then(() => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config }))
    const first = apiClient.get('/x', { adapter: ok as any })
    await Promise.resolve()
    expect(getPending()).toBe(1)
    release()
    await first
    expect(getPending()).toBe(0)
    const failing = (config: any) => Promise.reject(Object.assign(new Error('boom'), { config, response: { status: 500 } }))
    await apiClient.get('/y', { adapter: failing as any }).catch(() => undefined)
    expect(getPending()).toBe(0)
    expect(seen).toContain(1)
    stop()
  })
})

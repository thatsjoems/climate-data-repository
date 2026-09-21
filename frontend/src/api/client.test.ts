import { describe, it, expect, beforeEach } from 'vitest'
import apiClient from './client'

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
  })

  it('attaches the stored access token as a Bearer header', async () => {
    localStorage.setItem('cdr_token', 'abc123')
    const fulfilled = getRequestInterceptor()
    const config = await fulfilled({ headers: {} } as any)
    expect(config.headers.Authorization).toBe('Bearer abc123')
  })

  it('does not set an Authorization header when there is no stored token', async () => {
    const fulfilled = getRequestInterceptor()
    const config = await fulfilled({ headers: {} } as any)
    expect(config.headers.Authorization).toBeUndefined()
  })
})

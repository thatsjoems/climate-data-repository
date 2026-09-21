import { describe, it, expect, beforeEach } from 'vitest'
import apiClient from './client'

// The request interceptor is what makes every authenticated screen work at
// all - if it silently stopped attaching the access token, every request
// would look like an anonymous one to the backend. This is worth a direct
// test rather than only being exercised incidentally by other tests.

describe('apiClient request interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('attaches the stored access token as a Bearer header', async () => {
    localStorage.setItem('cdr_token', 'abc123')
    const config = await apiClient.interceptors.request.handlers[0].fulfilled({
      headers: {},
    } as any)
    expect(config.headers.Authorization).toBe('Bearer abc123')
  })

  it('does not set an Authorization header when there is no stored token', async () => {
    const config = await apiClient.interceptors.request.handlers[0].fulfilled({
      headers: {},
    } as any)
    expect(config.headers.Authorization).toBeUndefined()
  })
})

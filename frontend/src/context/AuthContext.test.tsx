import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import axios from 'axios'
import apiClient, { getAccessToken, setAccessToken, hasSessionHint, setSessionHint, WEB_CLIENT_HEADERS } from '../api/client'
import { AuthProvider, useAuth } from './AuthContext'

// Observation O2: nothing that can sign anyone in is kept in the browser's storage. The refresh token is an HttpOnly cookie the page cannot read, and
// the access token lives in memory. A reloaded page learns who is signed in by asking the server (POST /auth/refresh).

const USER = { id: 'u1', full_name: 'Test Analyst', username: 'analyst', email: 'a@example.com', role: 'BOT_USER', institution_id: null, must_change_password: false }

let latest: ReturnType<typeof useAuth>
function Probe() {
  latest = useAuth()
  return <div>{latest.ready ? (latest.user ? `signed in as ${latest.user.username}` : 'signed out') : 'checking'}</div>
}
function mount() {
  return render(<AuthProvider><Probe /></AuthProvider>)
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    setAccessToken(null)
  })
  afterEach(() => vi.restoreAllMocks())

  it('does not ask the server when this browser has never signed in', () => {
    const post = vi.spyOn(axios, 'post')
    mount()
    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it('asks the server on a reload, and shows the person it names, without any token in the storage', async () => {
    setSessionHint(true)
    vi.spyOn(axios, 'post').mockResolvedValue({ data: { access_token: 'fresh', user: USER } })
    mount()
    expect(screen.getByText('checking')).toBeInTheDocument()       // nobody is sent to the sign-in page while the answer is awaited
    await waitFor(() => expect(screen.getByText('signed in as analyst')).toBeInTheDocument())
    expect(getAccessToken()).toBe('fresh')
    expect(localStorage.getItem('cdr_token')).toBeNull()
    expect(localStorage.getItem('cdr_user')).toBeNull()
  })

  it('treats a refused refresh as signed out and forgets the hint', async () => {
    setSessionHint(true)
    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 401 } })
    mount()
    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument())
    expect(hasSessionHint()).toBe(false)
    expect(getAccessToken()).toBeNull()
  })

  it('signs in with the access token in memory only; the answer has no refresh token and nothing is stored', async () => {
    vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { access_token: 'tok', refresh_token: null, user: USER } })
    mount()
    await act(async () => { await latest.login('analyst', 'secret', 'internal') })
    expect(screen.getByText('signed in as analyst')).toBeInTheDocument()
    expect(getAccessToken()).toBe('tok')
    expect(localStorage.getItem('cdr_token')).toBeNull()
    expect(localStorage.getItem('cdr_refresh_token')).toBeNull()
    expect(localStorage.getItem('cdr_user')).toBeNull()
    expect(hasSessionHint()).toBe(true)
  })

  it('signs out: asks the server to end the session and delete the cookie, and forgets everything here', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { access_token: 'tok', user: USER } })
    mount()
    await act(async () => { await latest.login('analyst', 'secret') })
    post.mockResolvedValue({ data: { status: 'ok' } })
    act(() => latest.logout())
    expect(screen.getByText('signed out')).toBeInTheDocument()
    expect(getAccessToken()).toBeNull()
    expect(hasSessionHint()).toBe(false)
    expect(post).toHaveBeenLastCalledWith('/auth/logout', null, { headers: WEB_CLIENT_HEADERS })
  })
})

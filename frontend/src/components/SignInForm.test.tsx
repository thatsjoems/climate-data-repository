import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SignInForm from './SignInForm'
import * as AuthContext from '../context/AuthContext'
import apiClient from '../api/client'
import { portalOfRole, signInPath, rememberPortal, rememberedPortal, onlyStaff } from '../portal'

function mockAuth(login = vi.fn(), error: string | null = null) {
  vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
    user: null, login, logout: vi.fn(), refreshUser: vi.fn(), verifyCode: vi.fn(), beginMfaSetup: vi.fn(), confirmMfaSetup: vi.fn(),
    ready: true, isLoading: false, error,
  } as any)
  return login
}

function show(portal: 'internal' | 'external') {
  return render(<MemoryRouter><SignInForm portal={portal} /></MemoryRouter>)
}

describe('the two sign-in doors', () => {
  beforeEach(() => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { environment: 'production' } } as any)
  })
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.removeItem('cdr_portal')
  })

  it('shows the staff page as the Bank staff door, with its own badge and button', () => {
    mockAuth()
    show('internal')
    expect(screen.getByText('Bank of Tanzania - Staff sign-in')).toBeInTheDocument()
    expect(screen.getByTestId('login-badge')).toHaveTextContent('Bank staff only')
    expect(screen.getByRole('button', { name: 'Staff Log In' })).toBeInTheDocument()
    expect(document.querySelector('[data-portal="internal"]')).not.toBeNull()
  })

  it('shows the institutions page as the institutions door, without the staff badge', () => {
    mockAuth()
    show('external')
    expect(screen.getByText('Reporting institutions portal')).toBeInTheDocument()
    expect(screen.queryByTestId('login-badge')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log In' })).toBeInTheDocument()
    expect(document.querySelector('[data-portal="external"]')).not.toBeNull()
  })

  it('tells the server which door it is when someone signs in', async () => {
    const login = mockAuth(vi.fn().mockResolvedValue({ status: 'done' }))
    show('internal')
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'analyst' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Staff Log In' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('analyst', 'secret', 'internal'))
  })

  it('names the external door from the institutions page', async () => {
    const login = mockAuth(vi.fn().mockResolvedValue({ status: 'done' }))
    show('external')
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'bank1' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log In' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('bank1', 'secret', 'external'))
  })

  it('shows the server\'s answer when someone used the wrong door', () => {
    mockAuth(vi.fn(), 'This sign-in page is for Bank of Tanzania staff only. Institution users sign in at /login.')
    show('internal')
    expect(screen.getByRole('alert')).toHaveTextContent('Institution users sign in at /login')
  })

  it('shows the demonstration accounts of its own door only, and none in production', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { environment: 'development' } } as any)
    mockAuth()
    const { unmount } = show('internal')
    await waitFor(() => expect(screen.getByText(/BOT Analyst/)).toBeInTheDocument())
    expect(screen.queryByText(/bankA_user/)).not.toBeInTheDocument()
    unmount()
    show('external')
    await waitFor(() => expect(screen.getByText(/bankA_user/)).toBeInTheDocument())
    expect(screen.queryByText(/bot_analyst/)).not.toBeInTheDocument()
  })

  it('shows no demonstration accounts in production', async () => {
    mockAuth()
    show('external')
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
    expect(screen.queryByText(/DEMO accounts/)).not.toBeInTheDocument()
  })
})

describe('portal helpers', () => {
  afterEach(() => localStorage.removeItem('cdr_portal'))

  it('puts each role at one door', () => {
    expect(portalOfRole('BOT_USER')).toBe('internal')
    expect(portalOfRole('SYSTEM_ADMIN')).toBe('internal')
    expect(portalOfRole('INSTITUTION_USER')).toBe('external')
  })

  it('knows when a screen is for staff only', () => {
    expect(onlyStaff(['BOT_USER', 'SYSTEM_ADMIN'])).toBe(true)
    expect(onlyStaff(['SYSTEM_ADMIN'])).toBe(true)
    expect(onlyStaff(['INSTITUTION_USER'])).toBe(false)
    expect(onlyStaff(['BOT_USER', 'INSTITUTION_USER'])).toBe(false)
    expect(onlyStaff(undefined)).toBe(false)
    expect(onlyStaff([])).toBe(false)
  })

  it('remembers the door and defaults to the institutions\' page', () => {
    expect(rememberedPortal()).toBe('external')
    expect(signInPath()).toBe('/login')
    rememberPortal('internal')
    expect(rememberedPortal()).toBe('internal')
    expect(signInPath()).toBe('/staff/login')
    expect(signInPath('external')).toBe('/login')
  })
})

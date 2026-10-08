import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import * as AuthContext from '../context/AuthContext'
import apiClient from '../api/client'
import RecoveryCodesCard from './RecoveryCodesCard'

// The card that makes new recovery codes for someone who already uses two-step sign-in. It must appear only for them, ask for the CURRENT code, show the new
// codes once and say the old ones are dead, and show the server's message (not sign the person out) when the code is wrong.
vi.mock('../api/client', () => ({ default: { post: vi.fn() } }))

function signedInAs(mfaEnabled: boolean) {
  vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
    user: { id: 'u1', full_name: 'Test Admin', username: 'testadmin', email: 'a@example.com', role: 'SYSTEM_ADMIN', institution_id: null, must_change_password: false, mfa_enabled: mfaEnabled },
    login: vi.fn(), verifyCode: vi.fn(), beginMfaSetup: vi.fn(), confirmMfaSetup: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(), isLoading: false, error: null,
  } as any)
}

describe('RecoveryCodesCard', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows nothing to someone who does not use two-step sign-in', () => {
    signedInAs(false)
    const { container } = render(<RecoveryCodesCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('asks for the current code and, once it is right, shows the new codes and says the old ones are dead', async () => {
    signedInAs(true)
    ;(apiClient.post as any).mockResolvedValue({ data: { recovery_codes: ['AAAAA-11111', 'BBBBB-22222'] } })
    render(<RecoveryCodesCard />)
    fireEvent.change(screen.getByLabelText('Current 6-digit code'), { target: { value: '123 456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Make new recovery codes' }))
    await waitFor(() => expect(screen.getByText('AAAAA-11111')).toBeInTheDocument())
    expect(apiClient.post).toHaveBeenCalledWith('/auth/mfa/recovery-codes', { code: '123456' })   // the spaces are taken out
    expect(screen.getByText(/old codes no longer work/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled()                            // until the person says they saved them
  })

  it('shows the server message for a wrong code and no codes', async () => {
    signedInAs(true)
    ;(apiClient.post as any).mockRejectedValue({ response: { status: 401, data: { detail: 'That code is not right.' } } })
    render(<RecoveryCodesCard />)
    fireEvent.change(screen.getByLabelText('Current 6-digit code'), { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Make new recovery codes' }))
    await waitFor(() => expect(screen.getByText('That code is not right.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Make new recovery codes' })).toBeInTheDocument()   // the form is still there to try again
    expect(screen.queryByText('AAAAA-11111')).toBeNull()
  })

  it('does not let the button be pressed with fewer than 6 digits', () => {
    signedInAs(true)
    render(<RecoveryCodesCard />)
    fireEvent.change(screen.getByLabelText('Current 6-digit code'), { target: { value: '12345' } })
    expect(screen.getByRole('button', { name: 'Make new recovery codes' })).toBeDisabled()
  })
})

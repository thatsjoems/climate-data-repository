/**
 * The two sign-in doors: Bank staff (BOT analysts and System Administrators) at /staff/login, reporting institutions at /login.
 * The server checks the door too (backend app/core/portal.py); this only decides which page to show and where to send someone
 * who has to sign in again.
 */
export type Portal = 'internal' | 'external'

export const SIGN_IN_PATH: Record<Portal, string> = { internal: '/staff/login', external: '/login' }
const STAFF_ROLES = ['BOT_USER', 'SYSTEM_ADMIN']
const KEY = 'cdr_portal'

export function portalOfRole(role: string): Portal {
  return STAFF_ROLES.includes(role) ? 'internal' : 'external'
}

/** True when every one of these roles is Bank staff (a screen only staff may open). */
export function onlyStaff(roles?: string[]): boolean {
  return !!roles && roles.length > 0 && roles.every((r) => STAFF_ROLES.includes(r))
}

/** The door this browser last signed in through, so signing out or an expired session returns to the same page. */
export function rememberPortal(portal: Portal) {
  try { localStorage.setItem(KEY, portal) } catch { /* private window: the default door is used */ }
}

export function rememberedPortal(): Portal {
  try { return localStorage.getItem(KEY) === 'internal' ? 'internal' : 'external' } catch { return 'external' }
}

export function signInPath(portal: Portal = rememberedPortal()): string {
  return SIGN_IN_PATH[portal]
}

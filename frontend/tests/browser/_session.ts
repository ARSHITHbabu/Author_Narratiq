// Live-suite sign-in helper (Stage 10, task 10.7).
//
// The app's session is an HttpOnly cookie set by POST /api/auth/login; the
// response body no longer carries a token. The specs sign in ONCE per worker
// through the API (auth is rate-limited to 5/min per IP) and then:
//   * seed the browser context with the same cookies the app's own sign-in sets
//     (seedBrowserSession) — the page never sees a token, exactly as in use;
//   * call the API directly with the session token as a Bearer header, which
//     the backend still accepts for tooling (sessionToken).
import type { APIResponse, Page } from '@playwright/test'

const SESSION_COOKIE = 'narratiq_session'
const CSRF_COOKIE = 'narratiq_csrf'
const csrfFor = new Map<string, string>()

function cookieValue(res: APIResponse, name: string): string | null {
  for (const h of res.headersArray()) {
    if (h.name.toLowerCase() !== 'set-cookie') continue
    const m = h.value.match(new RegExp(`^${name}=([^;]*)`))
    if (m) return decodeURIComponent(m[1])
  }
  return null
}

/** The session token from a successful login response (and remember its CSRF pair). */
export function sessionToken(res: APIResponse): string {
  const token = cookieValue(res, SESSION_COOKIE)
  if (!token) throw new Error(`login response set no ${SESSION_COOKIE} cookie (status ${res.status()})`)
  const csrf = cookieValue(res, CSRF_COOKIE)
  if (csrf) csrfFor.set(token, csrf)
  return token
}

/** Put the session into the browser the way a real sign-in does: two cookies on
 *  the frontend's origin (the app talks to the API same-origin). */
export async function seedBrowserSession(page: Page, token: string): Promise<void> {
  const origin = new URL(process.env.E2E_BASE_URL ?? 'http://localhost:3000').origin
  const cookies = [{ name: SESSION_COOKIE, value: token, url: origin, httpOnly: true, sameSite: 'Lax' as const }]
  const csrf = csrfFor.get(token)
  if (csrf) cookies.push({ name: CSRF_COOKIE, value: csrf, url: origin, httpOnly: false, sameSite: 'Lax' as const })
  await page.context().addCookies(cookies)
}

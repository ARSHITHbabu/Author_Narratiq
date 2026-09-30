// Built-in frontend error reporting (Stage 10, task 10.2; decision S10-C).
//
// Sends a SHAPE of the failure — error name, message and stack frames, and the
// page's route pattern (ids replaced) — to POST /api/client-errors on
// NarratIQ's own backend. Nothing goes to any third party. The backend scrubs
// again before storing (services/error_tracking.py). Never throws; reporting
// must never make a failure worse.

const BASE = process.env.NEXT_PUBLIC_HTTP_API_BASE || ''
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi
const sent = new Set<string>()

export function routePattern(pathname: string): string {
  return pathname.replace(UUID, '<id>')
}

export function reportClientError(error: unknown, where = 'boundary'): void {
  try {
    if (typeof window === 'undefined') return
    const e = error instanceof Error ? error : new Error(String(error))
    const key = `${e.name}|${e.message}|${where}`
    if (sent.has(key)) return            // one report per distinct error per page load
    sent.add(key)
    const body = JSON.stringify({
      kind: (e.name || 'Error').slice(0, 120),
      message: `[${where}] ${e.message || ''}`.slice(0, 2000),
      stack: (e.stack || '').slice(0, 8000),
      route: routePattern(window.location.pathname).slice(0, 300),
    })
    void fetch(`${BASE}/api/client-errors`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true,
    }).catch(() => {})
  } catch {
    // swallow — see header
  }
}

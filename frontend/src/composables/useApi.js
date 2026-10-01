export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// FastAPI returns `detail` as a string, or as a list of {loc, msg} for validation errors.
function formatDetail(detail, status, statusText) {
  if (Array.isArray(detail)) {
    return detail.map(d => {
      const where = (d.loc || []).filter(x => x !== 'body').join('.')
      return where ? `${where}: ${d.msg}` : d.msg
    }).join('; ')
  }
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return statusText || `HTTP ${status}`
}

export function clearSession() {
  ;['token', 'username', 'role'].forEach(k => localStorage.removeItem(k))
}

export async function api(url, opts = {}) {
  const token = localStorage.getItem('token')
  const headers = { ...opts.headers }
  if (opts.body !== undefined && !headers['Content-Type']) headers['Content-Type'] = 'application/json'
  if (token) headers['Authorization'] = `Bearer ${token}`

  let res
  try {
    res = await fetch(url, { ...opts, headers })
  } catch (e) {
    throw new ApiError('Cannot reach SwitchPilot (network error)', 0)
  }

  const isLogin = url.startsWith('/api/auth/login')
  if (res.status === 401 && !isLogin) {
    // session expired or account removed: back to the login page, remembering where we were
    clearSession()
    const back = window.location.pathname + window.location.search
    const redirect = back && back !== '/login' ? `?redirect=${encodeURIComponent(back)}` : ''
    window.location.href = `/login${redirect}`
    throw new ApiError('Session expired', 401)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const message = formatDetail(body?.detail, res.status, res.statusText)
    throw new ApiError(res.status === 403 ? `Not allowed: ${message}` : message, res.status, body?.detail)
  }
  if (res.status === 204) return null
  return res.json()
}

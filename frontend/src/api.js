export async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: 'include', headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}, ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body })
  if (r.status === 401) { throw Object.assign(new Error('unauthenticated'), { status: 401 }) }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(data.detail || r.statusText), { status: r.status })
  return data
}
export const get = (p) => api(p)
export const post = (p, body) => api(p, { method: 'POST', body })
export const put = (p, body) => api(p, { method: 'PUT', body })
export const del = (p) => api(p, { method: 'DELETE' })
export const fmt = (iso) => iso ? new Date(iso).toLocaleString('en-IN', { hour12: true, dateStyle: 'medium', timeStyle: 'short' }) : ''
export const STATE_LABEL = { matched: 'Matched', queued: 'Queued', preparing: 'Preparing', awaiting_approval: 'Awaiting approval', submitting: 'Submitting', needs_human: 'Needs you',
  submitted: 'Submitted', viewed: 'Viewed by recruiter', in_process: 'In process', shortlisted: 'Shortlisted', rejected: 'Rejected', skipped: 'Skipped', failed: 'Failed' }

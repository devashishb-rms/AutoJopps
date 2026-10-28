import React, { useEffect, useState } from 'react'
import { get } from '../api.js'

export default function Admin() {
  const [s, setS] = useState(null)
  useEffect(() => { const f = () => get('/api/admin/stats').then(setS); f(); const t = setInterval(f, 4000); return () => clearInterval(t) }, [])
  if (!s) return <div>Loading…</div>
  const K = (n, l) => <div className="card kpi"><div className="n">{n}</div><div className="l">{l}</div></div>
  return <div>
    <div className="topbar"><div><h1>Admin: founder view</h1><div className="muted small">Live numbers from this instance. In production this is the operator console; customers never see it.</div></div></div>
    <div className="grid g4" style={{ marginBottom: 14 }}>{K(s.users, 'users')}{K(s.active_subscriptions, 'active subscriptions')}{K('₹' + s.mrr_inr.toLocaleString('en-IN'), 'MRR (gross)')}{K('₹' + s.net_mrr_inr.toLocaleString('en-IN'), 'MRR net of GST + fees')}</div>
    <div className="grid g4" style={{ marginBottom: 14 }}>{K(s.submitted_total, 'applications submitted')}{K(s.cost_per_application_inr ?? '—', 'cost per application (₹)')}{K(s.hitl_last_24h, 'human-help events, 24h')}{K(s.model_calls, 'model calls')}</div>
    <div className="grid g2">
      <div className="card"><h2>Applications by state</h2><table><tbody>{Object.entries(s.applications).map(([k, v]) => <tr key={k}><td>{k}</td><td><b>{v}</b></td></tr>)}</tbody></table></div>
      <div className="card"><h2>Cost meter</h2><table><tbody><tr><td>Browser minutes (₹)</td><td><b>{s.browser_cost_inr}</b></td></tr><tr><td>Model (₹)</td><td><b>{s.model_cost_inr}</b></td></tr><tr><td>Plans</td><td>{Object.entries(s.by_plan).map(([k, v]) => `${k}: ${v}`).join(', ') || '—'}</td></tr></tbody></table>
        <h3 style={{ marginTop: 12 }}>Portal skills</h3><table><thead><tr><th>Portal</th><th>v</th><th>Status</th><th>Runs</th><th>Repairs</th></tr></thead><tbody>{s.skills.map((k, i) => <tr key={i}><td>{k.portal}</td><td>{k.version}</td><td>{k.status}</td><td>{k.runs}</td><td>{k.repairs}</td></tr>)}</tbody></table>
        <h3 style={{ marginTop: 12 }}>Integration modes</h3><div>{Object.entries(s.modes).map(([k, v]) => <span key={k} className="tag">{k}: {String(v)}</span>)}</div></div>
    </div>
  </div>
}

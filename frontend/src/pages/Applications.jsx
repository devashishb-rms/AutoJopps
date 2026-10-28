import React, { useContext, useEffect, useState } from 'react'
import { Ctx } from '../App.jsx'
import { get, post, fmt, STATE_LABEL } from '../api.js'
import { HitlCard } from './Dashboard.jsx'

const GROUPS = { all: null, active: ['queued', 'preparing', 'submitting', 'needs_human', 'awaiting_approval'], applied: ['submitted', 'viewed', 'in_process', 'shortlisted', 'rejected'], matched: ['matched'], other: ['skipped', 'failed'] }

export default function Applications() {
  const { toast } = useContext(Ctx)
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('all')
  const [sel, setSel] = useState(null)
  const [det, setDet] = useState(null)
  const load = async () => { setData(await get('/api/applications')); if (sel) setDet(await get(`/api/applications/${sel}`)) }
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [sel])
  if (!data) return <div>Loading…</div>
  const rows = data.applications.filter(a => !GROUPS[tab] || GROUPS[tab].includes(a.state))
  return <div>
    <div className="topbar"><h1>Applications</h1><div className="row">{Object.keys(GROUPS).map(k => <button key={k} className={'btn sm ' + (tab === k ? '' : 'sec')} onClick={() => setTab(k)}>{k} ({data.applications.filter(a => !GROUPS[k] || GROUPS[k].includes(a.state)).length})</button>)}</div></div>
    <div className="grid" style={{ gridTemplateColumns: det ? '1fr 1fr' : '1fr' }}>
      <div className="card"><table><thead><tr><th>Role</th><th>Portal</th><th>Score</th><th>State</th><th>Updated</th><th></th></tr></thead><tbody>
        {rows.map(a => <tr key={a.id} style={sel === a.id ? { background: 'var(--accsoft)' } : {}}>
          <td><a href="#" onClick={e => { e.preventDefault(); setSel(a.id) }}><b>{a.job.title}</b></a><div className="muted small">{a.job.company} · {a.job.location} · {a.job.work_mode} · {a.job.salary}</div></td>
          <td className="small">{a.job.portal}{a.external_ref && <div className="mono">{a.external_ref}</div>}</td><td>{a.score}</td>
          <td><span className={'pill ' + a.state}>{STATE_LABEL[a.state]}</span></td><td className="small muted">{fmt(a.updated_at)}</td>
          <td>{['matched', 'skipped', 'failed'].includes(a.state) && <button className="btn sm sec" onClick={async () => { try { await post(`/api/agent/apply/${a.id}`); toast('Started'); setSel(a.id) } catch (x) { toast(x.message) } }}>Apply now</button>}</td></tr>)}
        {rows.length === 0 && <tr><td colSpan={6} className="muted">Nothing here yet.</td></tr>}
      </tbody></table></div>
      {det && <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}><h2>{det.job.title}</h2><button className="btn sm sec" onClick={() => { setSel(null); setDet(null) }}>Close</button></div>
        <p className="muted small">{det.job.company} · {det.job.location} · {det.job.exp} · {det.job.salary} · <a href={det.job.url} target="_blank" rel="noreferrer">open on portal ↗</a></p>
        <div>{(det.reasons || []).map(r => <span key={r} className="tag">{r}</span>)}</div>
        {(det.state === 'needs_human' || det.state === 'awaiting_approval') && <HitlCard app={det} onDone={load} />}
        {det.tailored?.summary && <div className="ok small"><b>Tailored note ({det.tailored.by}):</b> {det.tailored.headline} — {det.tailored.summary}</div>}
        <h3 style={{ marginTop: 12 }}>Timeline</h3>
        <table><tbody>{(det.history || []).map((h, i) => <tr key={i}><td className="small muted" style={{ whiteSpace: 'nowrap' }}>{fmt(h.at)}</td><td><span className={'pill ' + h.to}>{STATE_LABEL[h.to] || h.to}</span> <span className="small muted">{h.note}</span></td></tr>)}</tbody></table>
        <h3 style={{ marginTop: 12 }}>Run log</h3>
        <div className="log">{(det.logs || []).map(l => `${l.level === 'info' ? '·' : l.level === 'warn' ? '!' : 'x'} ${l.message}`).join('\n') || 'No run yet.'}</div>
        {det.has_proof && <div style={{ marginTop: 12 }}><h3>Proof of submission</h3><img src={`/api/applications/${det.id}/proof?t=${det.updated_at}`} alt="proof" style={{ width: '100%', border: '1px solid var(--line)', borderRadius: 8 }} /></div>}
        <p className="small muted" style={{ marginTop: 8 }}>Browser cost for this application: ₹{det.cost_inr}</p>
      </div>}
    </div>
  </div>
}

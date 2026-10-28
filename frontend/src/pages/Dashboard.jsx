import React, { useContext, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Ctx } from '../App.jsx'
import { get, post, fmt, STATE_LABEL } from '../api.js'

export default function Dashboard() {
  const { user, refresh, toast } = useContext(Ctx)
  const [st, setSt] = useState(null)
  const [apps, setApps] = useState(null)
  const [notes, setNotes] = useState([])
  const [err, setErr] = useState('')
  const load = async () => { try { const [a, b, c] = await Promise.all([get('/api/agent/status'), get('/api/applications'), get('/api/notifications')]); setSt(a); setApps(b); setNotes(c) } catch (x) { setErr(x.message) } }
  useEffect(() => { load(); const t = setInterval(load, 2500); return () => clearInterval(t) }, [])
  if (!st || !apps) return <div>Loading…</div>
  const toggle = async () => { setErr(''); try { await post('/api/agent/toggle', { enabled: !st.enabled }); await refresh(); await load() } catch (x) { setErr(x.message) } }
  const waiting = apps.applications.filter(a => a.state === 'needs_human' || a.state === 'awaiting_approval')
  const active = apps.applications.find(a => a.id === st.active_application)
  const f = apps.funnel
  return <div>
    <div className="topbar"><div><h1>Overview</h1><div className="muted small">Plan: <b>{st.plan ? st.plan[0].toUpperCase() + st.plan.slice(1) : 'none'}</b> · today {st.used_today} · this month {st.used_month}</div></div>
      <div className="row">
        <button className="btn sec" onClick={async () => { const r = await post('/api/agent/discover'); toast(`Discovered ${r.new_jobs} new jobs, scored ${r.scored}`); load() }}>Discover jobs</button>
        <button className={'btn ' + (st.enabled ? 'bad' : '')} onClick={toggle}>{st.enabled ? 'Pause agent' : 'Start agent'}</button>
      </div></div>
    {err && <div className="alert">{err}</div>}
    <div className="grid g4" style={{ marginBottom: 14 }}>
      {[['Submitted', f.submitted], ['Viewed by recruiter', f.viewed], ['In process', f.in_process], ['Shortlisted', f.shortlisted]].map(([l, n]) => <div key={l} className="card kpi"><div className="n">{n}</div><div className="l">{l}</div></div>)}
    </div>
    <div className="grid g2">
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}><h2>Live agent</h2><span className={'pill ' + (st.enabled ? 'submitted' : '')}>{st.enabled ? (st.running ? 'running' : 'idle, waiting for next slot') : 'paused'}</span></div>
        {active ? <div><p><b>{active.job.title}</b> at {active.job.company} · <span className={'pill ' + active.state}>{STATE_LABEL[active.state]}</span></p>
          {(active.state === 'needs_human' || active.state === 'awaiting_approval') ? <HitlCard app={active} onDone={load} /> : <LiveView appId={active.id} compact />}
        </div> : <p className="muted">No application in progress. {st.enabled ? 'The next matched job starts on the next tick.' : 'Start the agent to begin.'}</p>}
      </div>
      <div className="card">
        <h2>Funnel</h2>
        <div className="funnel" style={{ marginTop: 10 }}>{[['Discovered', f.discovered], ['Matched', f.matched], ['Submitted', f.submitted], ['Viewed', f.viewed], ['In process', f.in_process], ['Shortlisted', f.shortlisted]].map(([l, n]) =>
          <div key={l} style={{ height: `${Math.max(14, 100 * n / Math.max(1, f.discovered))}%` }}><b>{n}</b>{l}</div>)}</div>
        <h3 style={{ marginTop: 16 }}>Needs you ({waiting.length})</h3>
        {waiting.length === 0 ? <p className="muted small">Nothing waiting. You will be alerted by email / WhatsApp (per your consent) and here.</p>
          : waiting.map(a => <div key={a.id} className="alert"><b>{a.job.title}</b> at {a.job.company}: {a.hitl.kind === 'question' ? a.hitl.question : a.hitl.kind}{a.id !== st.active_application && <> · <Link to="/app/applications">open</Link></>}</div>)}
        <h3 style={{ marginTop: 16 }}>Recent alerts</h3>
        <table><tbody>{notes.slice(0, 6).map(n => <tr key={n.id}><td className="small">{n.title}<div className="muted">{n.body}</div></td><td className="small muted" style={{ whiteSpace: 'nowrap' }}>{n.channel}{n.delivered !== 'in_app' && ` · ${n.delivered}`}<br />{fmt(n.at)}</td></tr>)}</tbody></table>
      </div>
    </div>
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}><h2>Top matches</h2><Link to="/app/applications">All applications →</Link></div>
      <table><thead><tr><th>Score</th><th>Role</th><th>Why</th><th>State</th><th></th></tr></thead><tbody>
        {apps.applications.filter(a => a.state !== 'skipped' || a.score >= 25).sort((a, b) => b.score - a.score).slice(0, 8).map(a => <tr key={a.id}>
          <td><b>{a.score}</b></td><td><b>{a.job.title}</b><div className="muted small">{a.job.company} · {a.job.location} · {a.job.salary}</div></td>
          <td className="small">{(a.reasons || []).map(r => <span key={r} className="tag">{r}</span>)}</td><td><span className={'pill ' + a.state}>{STATE_LABEL[a.state]}</span></td>
          <td>{['matched', 'skipped', 'failed'].includes(a.state) && <button className="btn sm sec" onClick={async () => { try { await post(`/api/agent/apply/${a.id}`); toast('Started'); load() } catch (x) { setErr(x.message) } }}>Apply now</button>}</td></tr>)}
      </tbody></table>
    </div>
  </div>
}

export function HitlCard({ app, onDone }) {
  const { toast } = useContext(Ctx)
  const [val, setVal] = useState(app.hitl.suggestion || '')
  const [phone, setPhone] = useState(null)
  const [busy, setBusy] = useState(false)
  const h = app.hitl
  useEffect(() => { setVal(h.suggestion || ''); setPhone(null) }, [h.created_at])
  useEffect(() => { if (h.kind !== 'otp') return; const t = setInterval(async () => setPhone(await get('/api/agent/demo-phone')), 1500); return () => clearInterval(t) }, [h.kind])
  const send = async (body) => { setBusy(true); try { await post(`/api/agent/hitl/${app.id}`, body); toast('Sent to the bot'); onDone && onDone() } finally { setBusy(false) } }
  const title = { login: 'One-time sign-in needed', otp: 'OTP needed', captcha: 'Human check', question: 'A question only you can answer', approve: 'Approve submission' }[h.kind]
  return <div className="alert" style={{ padding: 14 }}>
    <h3>{title}</h3><p className="small">{h.hint || h.question}</p>
    {h.kind === 'login' && <div><LiveView appId={app.id} />
      <div className="row" style={{ marginTop: 8 }}><button className="btn sm sec" disabled={busy} onClick={async () => { await post(`/api/agent/hitl/${app.id}/demo-login`); toast('Typed the mock-portal demo credentials (recorded as a demonstration)') }}>Demo: type portal credentials for me</button>
        <button className="btn sm" disabled={busy} onClick={async () => { await post(`/api/agent/hitl/${app.id}/login-done`); onDone && onDone() }}>I have signed in, continue</button>
        <button className="btn sm bad" onClick={() => send({ action: 'skip' })}>Skip this job</button></div>
      <p className="small muted">Click and type directly on the live screen. Your keystrokes go to the bot's browser; nothing is stored except the portal session afterwards.</p></div>}
    {h.kind === 'otp' && <div>{phone?.otp && <div className="ok small">Simulated phone (mock portal only): SMS received: your JobHub OTP is <b className="mono">{phone.otp}</b></div>}
      <div className="row"><input style={{ maxWidth: 160 }} placeholder="4-digit OTP" value={val} onChange={e => setVal(e.target.value)} /><button className="btn" disabled={busy || !val} onClick={() => send({ action: 'value', value: val })}>Submit OTP</button><button className="btn sec" onClick={() => send({ action: 'skip' })}>Skip</button></div></div>}
    {h.kind === 'captcha' && <div><LiveView appId={app.id} /><div className="row" style={{ marginTop: 8 }}><input style={{ maxWidth: 220 }} placeholder="Type the word you see" value={val} onChange={e => setVal(e.target.value)} /><button className="btn" disabled={busy || !val} onClick={() => send({ action: 'value', value: val })}>Submit</button><button className="btn sec" onClick={() => send({ action: 'skip' })}>Skip</button></div></div>}
    {h.kind === 'question' && <div>{h.suggestion && <p className="small muted">Suggested from your profile ({h.source}): "{h.suggestion}"</p>}
      <textarea rows={2} value={val} onChange={e => setVal(e.target.value)} placeholder="Your answer. It is remembered for next time." />
      <div className="row" style={{ marginTop: 8 }}><button className="btn" disabled={busy || !val} onClick={() => send({ action: 'value', value: val })}>Answer and remember</button><button className="btn sec" onClick={() => send({ action: 'skip' })}>Skip this job</button></div></div>}
    {h.kind === 'approve' && <div><LiveView appId={app.id} /><div className="row" style={{ marginTop: 8 }}><button className="btn" disabled={busy} onClick={() => send({ action: 'approve' })}>Approve and submit</button><button className="btn sec" onClick={() => send({ action: 'skip' })}>Do not submit</button></div></div>}
  </div>
}

export function LiveView({ appId, compact }) {
  const [frame, setFrame] = useState(null)
  const [url, setUrl] = useState('')
  const [ended, setEnded] = useState(false)
  const ws = useRef(null)
  const img = useRef(null)
  const [rec, setRec] = useState(false)
  useEffect(() => {
    setEnded(false); setFrame(null)
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const s = new WebSocket(`${proto}://${location.host}/api/live/${appId}`)
    ws.current = s
    s.onmessage = (e) => { const m = JSON.parse(e.data); if (m.type === 'frame') { setFrame(m.jpeg); setUrl(m.url) } else if (m.type === 'ended') setEnded(true) }
    s.onclose = () => setEnded(true)
    return () => s.close()
  }, [appId])
  const send = (o) => ws.current && ws.current.readyState === 1 && ws.current.send(JSON.stringify(o))
  const click = (e) => { const r = img.current.getBoundingClientRect(); send({ type: 'click', x: (e.clientX - r.left) * 1100 / r.width, y: (e.clientY - r.top) * 760 / r.height }); img.current.focus() }
  const key = (e) => { e.preventDefault(); if (e.key.length === 1) send({ type: 'type', text: e.key }); else if (['Enter', 'Backspace', 'Tab', 'Escape', 'ArrowDown', 'ArrowUp'].includes(e.key)) send({ type: 'key', key: e.key }) }
  if (ended && !frame) return <p className="muted small">The bot's browser for this application has closed.</p>
  return <div>
    <div className="live" style={compact ? { maxWidth: 560 } : {}}>
      {frame ? <img ref={img} tabIndex={0} src={`data:image/jpeg;base64,${frame}`} alt="Live browser" onClick={click} onKeyDown={key} /> : <div style={{ padding: 40, color: '#ccc', textAlign: 'center' }}>Connecting to the bot's browser…</div>}
      {url && <div className="url">{url.replace(location.origin, '')}</div>}
    </div>
    {!compact && <div className="row small muted" style={{ marginTop: 6 }}><span>Click on the screen to focus a field, then type. </span>
      <label className="row" style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={rec} onChange={e => { setRec(e.target.checked); send({ type: 'record', on: e.target.checked }) }} />record this as a demonstration (learning)</label></div>}
  </div>
}

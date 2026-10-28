import React, { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ctx } from '../App.jsx'
import { get, post, put } from '../api.js'
import PlanPicker from './PlanPicker.jsx'

const STEPS = ['Resume', 'Your profile', 'Job targets', 'Target JDs', 'Alerts & consent', 'Plan', 'Connect Gmail', 'Go live']
const WORK = ['remote', 'hybrid', 'wfo']

export default function Onboarding() {
  const { user, refresh, toast } = useContext(Ctx)
  const nav = useNavigate()
  const [step, setStep] = useState(Math.min(user.onboarding_step, 7))
  const [p, setP] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const load = async () => setP(await get('/api/profile'))
  useEffect(() => { load() }, [])
  if (!p) return <div>Loading…</div>
  const go = async (n) => { setErr(''); await refresh(); await load(); setStep(n) }
  const wrap = async (fn, next) => { setBusy(true); setErr(''); try { await fn(); await go(next) } catch (x) { setErr(x.message) } finally { setBusy(false) } }
  const d = p.data || {}, pr = p.preferences || {}

  return (
    <div>
      <div className="topbar"><h1>Set up AutoJopps</h1><span className="muted small">About 5 minutes. You can change everything later.</span></div>
      <div className="steps">{STEPS.map((s, i) => <div key={s} className={i === step ? 'on' : i < step ? 'done' : ''}>{i + 1}. {s}</div>)}</div>
      {err && <div className="alert">{err}</div>}

      {step === 0 && <div className="card">
        <h2>Upload your resume</h2>
        <p className="muted">PDF, DOCX or TXT. We read it to pre-fill the next form; you review every field.</p>
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={async e => {
          const f = e.target.files[0]; if (!f) return
          const fd = new FormData(); fd.append('file', f)
          await wrap(async () => { const r = await post('/api/profile/resume', fd); toast(`Parsed with ${r.parser} parser`) }, 1)
        }} />
        {p.resume && <p className="small">Current: <b>{p.resume.filename}</b> ({p.resume.parser}) · <a href="#" onClick={e => { e.preventDefault(); go(1) }}>keep it and continue</a></p>}
      </div>}

      {step === 1 && <FormStep d={d} busy={busy} onSave={(data) => wrap(() => put('/api/profile/form', { data }), 2)} back={() => setStep(0)} />}

      {step === 2 && <PrefsStep pr={pr} d={d} busy={busy} onSave={(preferences) => wrap(() => put('/api/profile/preferences', { preferences }), 3)} back={() => setStep(1)} />}

      {step === 3 && <JDStep jds={p.target_jds} busy={busy} onSave={(target_jds) => wrap(() => put('/api/profile/target-jds', { target_jds }), 4)} back={() => setStep(2)} />}

      {step === 4 && <NotifyStep nf={p.notify} email={user.email} busy={busy} onSave={(body) => wrap(() => put('/api/profile/notify', body), 5)} back={() => setStep(3)} />}

      {step === 5 && <div className="card"><h2>Choose a plan</h2><p className="muted">Caps are enforced per day and per month. Change or cancel any time.</p>
        <PlanPicker onDone={() => go(6)} /><div className="row" style={{ marginTop: 10 }}><button className="btn sec" onClick={() => setStep(4)}>Back</button></div></div>}

      {step === 6 && <GmailStep onDone={() => wrap(() => put('/api/profile/step', { step: 7 }), 7)} back={() => setStep(5)} />}

      {step === 7 && <div className="card"><h2>You are set</h2>
        <p>AutoJopps will discover roles on connected portals, score them against your targets, and apply within your plan's caps. The first time it meets a portal it will ask you to sign in once in the live view; it never stores your password.</p>
        <div className="ok">Human help is a normal part of the flow: when an OTP, a human check or an unusual question comes up, you get an alert and a one-tap way to help.</div>
        <div className="row"><button className="btn" disabled={busy} onClick={async () => { setBusy(true); try { await post('/api/agent/toggle', { enabled: true }); await refresh(); nav('/app') } catch (x) { setErr(x.message) } finally { setBusy(false) } }}>Start applying</button>
          <button className="btn sec" onClick={async () => { await refresh(); nav('/app') }}>Go to overview without starting</button></div></div>}
    </div>
  )
}

function FormStep({ d, onSave, busy, back }) {
  const [f, setF] = useState({ name: d.name || '', email: d.email || '', phone: d.phone || '', location: d.location || '', headline: d.headline || '',
    summary: d.summary || '', total_experience_years: d.total_experience_years || '', current_designation: d.current_designation || '',
    current_company: d.current_company || '', current_ctc_lpa: d.current_ctc_lpa || '', notice_period_days: d.notice_period_days || 30,
    education: (d.education || []).map(e => `${e.degree || ''} ${e.institute || ''} ${e.year || ''}`.trim()).filter(Boolean).join('; '),
    skills: (d.skills || []).join(', ') })
  const conf = d._confidence || {}
  const low = (k) => conf[k] !== undefined && conf[k] < 0.5
  const I = (k, label, type = 'text') => <div><label>{label}{low(k) && <span className="muted"> · please check</span>}</label><input type={type} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} style={low(k) ? { borderColor: 'var(--warn)' } : {}} /></div>
  return <div className="card"><h2>Your profile</h2><p className="muted">Pre-filled from your resume (a Naukri-style candidate form). Fields marked "please check" had low confidence.</p>
    <div className="grid g2">{I('name', 'Full name')}{I('email', 'Email')}{I('phone', 'Mobile')}{I('location', 'Current location')}
      {I('current_designation', 'Current designation')}{I('current_company', 'Current company')}{I('total_experience_years', 'Total experience (years)', 'number')}
      {I('current_ctc_lpa', 'Current CTC (LPA)', 'number')}{I('notice_period_days', 'Notice period (days)', 'number')}{I('education', 'Education')}</div>
    {I('headline', 'Headline')}<label>Summary</label><textarea rows={3} value={f.summary} onChange={e => setF({ ...f, summary: e.target.value })} />
    <label>Skills (comma separated)</label><input value={f.skills} onChange={e => setF({ ...f, skills: e.target.value })} />
    <div className="row" style={{ marginTop: 14 }}><button className="btn sec" onClick={back}>Back</button>
      <button className="btn" disabled={busy} onClick={() => onSave({ ...f, total_experience_years: +f.total_experience_years || 0, current_ctc_lpa: +f.current_ctc_lpa || 0, notice_period_days: +f.notice_period_days || 0,
        skills: f.skills.split(',').map(s => s.trim()).filter(Boolean), education: f.education ? [{ institute: f.education }] : [] })}>Save and continue</button></div></div>
}

function PrefsStep({ pr, d, onSave, busy, back }) {
  const [f, setF] = useState({ job_types: (pr.job_types || ['full-time']).join(', '), designations: (pr.designations || [d.current_designation].filter(Boolean)).join(', '),
    skills: (pr.skills || d.skills || []).join(', '), experience_years: pr.experience_years || d.total_experience_years || '', salary_min_lpa: pr.salary_min_lpa || '',
    salary_max_lpa: pr.salary_max_lpa || '', locations: (pr.locations || [d.location].filter(Boolean)).join(', '), work_modes: pr.work_modes || ['remote', 'hybrid'], relocate: !!pr.relocate })
  const tog = (m) => setF({ ...f, work_modes: f.work_modes.includes(m) ? f.work_modes.filter(x => x !== m) : [...f.work_modes, m] })
  const L = (s) => s.split(',').map(x => x.trim()).filter(Boolean)
  return <div className="card"><h2>What should we apply to?</h2>
    <div className="grid g2">
      <div><label>Job types</label><input value={f.job_types} onChange={e => setF({ ...f, job_types: e.target.value })} placeholder="full-time, contract" /></div>
      <div><label>Designations (comma separated)</label><input value={f.designations} onChange={e => setF({ ...f, designations: e.target.value })} placeholder="CTO, Head of Engineering" /></div>
      <div><label>Experience to present (years)</label><input type="number" value={f.experience_years} onChange={e => setF({ ...f, experience_years: e.target.value })} /></div>
      <div><label>Compensation range (LPA)</label><div className="row"><input type="number" placeholder="min" value={f.salary_min_lpa} onChange={e => setF({ ...f, salary_min_lpa: e.target.value })} /><input type="number" placeholder="max" value={f.salary_max_lpa} onChange={e => setF({ ...f, salary_max_lpa: e.target.value })} /></div></div>
      <div><label>Locations (comma separated; Remote counts everywhere)</label><input value={f.locations} onChange={e => setF({ ...f, locations: e.target.value })} /></div>
      <div><label>Work mode</label><div className="row">{WORK.map(m => <label key={m} className="row" style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={f.work_modes.includes(m)} onChange={() => tog(m)} />{m === 'wfo' ? 'office (WFO)' : m}</label>)}
        <label className="row" style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={f.relocate} onChange={e => setF({ ...f, relocate: e.target.checked })} />open to relocate</label></div></div>
    </div>
    <label>Skills you have (used for matching)</label><input value={f.skills} onChange={e => setF({ ...f, skills: e.target.value })} />
    <div className="row" style={{ marginTop: 14 }}><button className="btn sec" onClick={back}>Back</button>
      <button className="btn" disabled={busy} onClick={() => onSave({ job_types: L(f.job_types), designations: L(f.designations), skills: L(f.skills).map(s => s.toLowerCase()), experience_years: +f.experience_years || 0,
        salary_min_lpa: +f.salary_min_lpa || 0, salary_max_lpa: +f.salary_max_lpa || 0, locations: L(f.locations), work_modes: f.work_modes, relocate: f.relocate })}>Save and continue</button></div></div>
}

function JDStep({ jds, onSave, busy, back }) {
  const [list, setList] = useState(jds?.length ? jds : [{ title: '', company: '', text: '' }])
  const up = (i, k, v) => setList(list.map((j, idx) => idx === i ? { ...j, [k]: v } : j))
  return <div className="card"><h2>2–3 target job descriptions</h2><p className="muted">Paste JDs of roles you would love. Matching and tailoring are anchored on these.</p>
    {list.map((j, i) => <div key={i} className="card" style={{ margin: '10px 0' }}><div className="grid g2"><div><label>Title</label><input value={j.title} onChange={e => up(i, 'title', e.target.value)} /></div><div><label>Company (optional)</label><input value={j.company} onChange={e => up(i, 'company', e.target.value)} /></div></div>
      <label>Job description</label><textarea rows={4} value={j.text} onChange={e => up(i, 'text', e.target.value)} /></div>)}
    <div className="row">{list.length < 3 && <button className="btn sec" onClick={() => setList([...list, { title: '', company: '', text: '' }])}>Add another</button>}
      {list.length > 1 && <button className="btn sec" onClick={() => setList(list.slice(0, -1))}>Remove last</button>}</div>
    <div className="row" style={{ marginTop: 14 }}><button className="btn sec" onClick={back}>Back</button><button className="btn" disabled={busy} onClick={() => onSave(list)}>Save and continue</button></div></div>
}

function NotifyStep({ nf, email, onSave, busy, back }) {
  const [f, setF] = useState({ email: nf?.email || email, whatsapp: nf?.whatsapp || '', email_consent: nf?.email_consent ?? true, whatsapp_consent: nf?.whatsapp_consent ?? false })
  return <div className="card"><h2>Where should we reach you when a human is needed?</h2>
    <div className="grid g2"><div><label>Email</label><input value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></div>
      <div><label>WhatsApp number (with country code)</label><input value={f.whatsapp} onChange={e => setF({ ...f, whatsapp: e.target.value })} placeholder="+91 98xxxxxxxx" /></div></div>
    <label className="row" style={{ marginTop: 12 }}><input type="checkbox" style={{ width: 'auto' }} checked={f.email_consent} onChange={e => setF({ ...f, email_consent: e.target.checked })} />I agree to receive email alerts about my applications and when my help is needed.</label>
    <label className="row"><input type="checkbox" style={{ width: 'auto' }} checked={f.whatsapp_consent} onChange={e => setF({ ...f, whatsapp_consent: e.target.checked })} />I give permission to send WhatsApp messages to this number for the same purpose. (You can withdraw this any time in settings.)</label>
    <p className="small muted">Consent and its time are recorded, as required under India's DPDP Act. In-app alerts are always on.</p>
    <div className="row" style={{ marginTop: 14 }}><button className="btn sec" onClick={back}>Back</button><button className="btn" disabled={busy} onClick={() => onSave(f)}>Save and continue</button></div></div>
}

function GmailStep({ onDone, back }) {
  const { user, cfg, refresh, toast } = useContext(Ctx)
  const live = cfg?.modes?.google === 'live' && cfg?.modes?.gmail_scope
  const [mails, setMails] = useState(null)
  return <div className="card"><h2>Connect the Gmail account you use on job portals</h2>
    <p className="muted">Two things happen here. (1) The bot signs in to portals through <b>your</b> Google account only when you do it yourself in the live view; we store the portal session, never your Google password (Google blocks automated sign-ins). (2) Optionally, read-only Gmail access lets us detect recruiter replies and "viewed" notices to update tracking.</p>
    {user.gmail_connected ? <div className="ok">Gmail connected for {user.email}. <button className="btn sm sec" onClick={async () => setMails((await get('/api/auth/gmail/recent')).messages)}>Preview recruiter mails</button></div>
      : live ? <a className="btn" href="/api/auth/google/start?gmail=1" style={{ textDecoration: 'none' }}>Authorize Gmail (read-only)</a>
        : <div><div className="alert">Gmail read scope is not enabled in this build (it needs Google verification for public use). The prototype uses a forwarding alias instead.</div>
          <button className="btn" onClick={async () => { const r = await post('/api/auth/gmail/demo-connect'); await refresh(); toast(`Connected via ${r.mode}: forward recruiter mails to ${r.alias}`) }}>Connect with forwarding alias</button></div>}
    {mails && <table style={{ marginTop: 10 }}><thead><tr><th>Subject</th><th>From</th><th>When</th></tr></thead><tbody>{mails.map((m, i) => <tr key={i}><td>{m.subject}</td><td>{m.from}</td><td>{m.date}</td></tr>)}</tbody></table>}
    <div className="row" style={{ marginTop: 14 }}><button className="btn sec" onClick={back}>Back</button><button className="btn" onClick={onDone}>Continue</button></div></div>
}

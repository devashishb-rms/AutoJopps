import React, { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Ctx } from '../App.jsx'
import { get, post, put } from '../api.js'

export default function Settings() {
  const { user, refresh, toast } = useContext(Ctx)
  const nav = useNavigate()
  const [p, setP] = useState(null)
  useEffect(() => { get('/api/profile').then(setP) }, [])
  if (!p) return <div>Loading…</div>
  const d = p.data || {}, pr = p.preferences || {}, nf = p.notify || {}
  return <div>
    <div className="topbar"><h1>Profile &amp; settings</h1><button className="btn sec" onClick={() => nav('/app/onboarding')}>Edit via the setup wizard</button></div>
    <div className="grid g2">
      <div className="card"><h2>Profile</h2><table><tbody>
        {[['Name', d.name], ['Email', user.email], ['Mobile', d.phone], ['Designation', d.current_designation], ['Experience', d.total_experience_years && `${d.total_experience_years} years`], ['Current CTC', d.current_ctc_lpa && `${d.current_ctc_lpa} LPA`], ['Notice period', d.notice_period_days && `${d.notice_period_days} days`], ['Resume', p.resume?.filename]].map(([k, v]) => <tr key={k}><td className="muted small">{k}</td><td>{v || '—'}</td></tr>)}
      </tbody></table><div>{(d.skills || []).map(s => <span key={s} className="tag">{s}</span>)}</div></div>
      <div className="card"><h2>Targets</h2><table><tbody>
        {[['Designations', (pr.designations || []).join(', ')], ['Locations', (pr.locations || []).join(', ')], ['Work mode', (pr.work_modes || []).join(', ')], ['Pay floor', pr.salary_min_lpa && `${pr.salary_min_lpa} LPA`], ['Target JDs', (p.target_jds || []).map(j => j.title).join(' · ')]].map(([k, v]) => <tr key={k}><td className="muted small">{k}</td><td>{v || '—'}</td></tr>)}
      </tbody></table>
        <h3 style={{ marginTop: 14 }}>Approval</h3>
        <label className="row"><input type="radio" style={{ width: 'auto' }} checked={user.approval_mode === 'auto'} onChange={async () => { await put('/api/profile/settings', { approval_mode: 'auto' }); refresh(); toast('Auto-submit on') }} />Submit automatically within my caps</label>
        <label className="row"><input type="radio" style={{ width: 'auto' }} checked={user.approval_mode === 'approve_each'} onChange={async () => { await put('/api/profile/settings', { approval_mode: 'approve_each' }); refresh(); toast('You will approve each submission') }} />Ask me before every submission</label>
        <h3 style={{ marginTop: 14 }}>Alerts &amp; consent</h3>
        <p className="small">Email: {nf.email || '—'} ({nf.email_consent ? 'consented' : 'off'}) · WhatsApp: {nf.whatsapp || '—'} ({nf.whatsapp_consent ? 'consented' : 'off'}){nf.consent_at && <span className="muted"> · recorded {nf.consent_at.slice(0, 19).replace('T', ' ')} UTC</span>}</p>
        <h3 style={{ marginTop: 14 }}>Your data (DPDP)</h3>
        <p className="small muted">Delete the resume, profile, answers, recordings, applications and notifications we hold for you. Your sign-in remains so you can start again.</p>
        <button className="btn bad sm" onClick={async () => { if (confirm('Delete all my data?')) { await post('/api/profile/delete-my-data'); await refresh(); toast('Deleted'); nav('/app/onboarding') } }}>Delete my data</button>
      </div>
    </div>
  </div>
}

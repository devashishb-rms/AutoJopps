import React, { useContext, useEffect, useState } from 'react'
import { Ctx } from '../App.jsx'
import { get, post, put, del, fmt } from '../api.js'

export default function Learning() {
  const { toast } = useContext(Ctx)
  const [d, setD] = useState(null)
  const [q, setQ] = useState(''); const [a, setA] = useState('')
  const [open, setOpen] = useState(null)
  const load = async () => setD(await get('/api/learning'))
  useEffect(() => { load() }, [])
  if (!d) return <div>Loading…</div>
  return <div>
    <div className="topbar"><div><h1>Learning</h1><div className="muted small">What the bot has learned from you and from each portal. Answers are yours alone; portal skills share only page structure.</div></div>
      <div className="row"><button className="btn sec sm" onClick={async () => { await post('/api/agent/chaos?on=1'); toast('Chaos on: the mock portal renamed its form fields. Run an application to watch self-heal.') }}>Demo: break the portal</button>
        <button className="btn sec sm" onClick={async () => { await post('/api/agent/chaos?on=0'); toast('Chaos off') }}>Fix the portal</button></div></div>
    <div className="grid g2">
      <div className="card"><h2>Answer memory ({d.answers.length})</h2><p className="small muted">Screening questions you confirmed once. Reused on later applications; edit or delete any time.</p>
        <table><thead><tr><th>Question</th><th>Answer</th><th>Source</th><th>Uses</th><th></th></tr></thead><tbody>
          {d.answers.map(r => <tr key={r.id}><td className="small">{r.question}</td><td><input defaultValue={r.answer} onBlur={async e => { if (e.target.value !== r.answer) { await put(`/api/learning/answers/${r.id}`, { question: r.question, answer: e.target.value }); toast('Updated'); load() } }} /></td>
            <td className="small muted">{r.source}</td><td>{r.uses}</td><td><button className="btn sm bad" onClick={async () => { await del(`/api/learning/answers/${r.id}`); load() }}>×</button></td></tr>)}
        </tbody></table>
        <div className="row" style={{ marginTop: 10 }}><input placeholder="Question" value={q} onChange={e => setQ(e.target.value)} /><input placeholder="Answer" value={a} onChange={e => setA(e.target.value)} /><button className="btn sm" disabled={!q || !a} onClick={async () => { await post('/api/learning/answers', { question: q, answer: a }); setQ(''); setA(''); load() }}>Add</button></div>
      </div>
      <div className="card"><h2>Portal skills ({d.skills.length})</h2><p className="small muted">Versioned step lists per portal. A repaired or recorded skill starts as draft or trial and is promoted after clean runs.</p>
        <table><thead><tr><th>Portal</th><th>v</th><th>Status</th><th>Origin</th><th>Runs</th><th>Repairs</th><th></th></tr></thead><tbody>
          {d.skills.map(s => <tr key={s.id}><td>{s.portal}</td><td>{s.version}</td><td><span className={'pill ' + (s.status === 'active' ? 'submitted' : s.status === 'trial' ? 'needs_human' : '')}>{s.status}</span></td><td className="small">{s.origin}</td><td>{s.successes}/{s.runs}</td><td>{s.repairs}</td>
            <td className="row"><button className="btn sm sec" onClick={() => setOpen(open === s.id ? null : s.id)}>steps</button>{s.status !== 'active' && <button className="btn sm" onClick={async () => { await put(`/api/learning/skills/${s.id}`, { status: 'active' }); toast('Promoted'); load() }}>promote</button>}{s.status !== 'retired' && d.skills.filter(x => x.portal === s.portal && x.status === 'active').length > (s.status === 'active' ? 1 : 0) && <button className="btn sm sec" onClick={async () => { await put(`/api/learning/skills/${s.id}`, { status: 'retired' }); toast('Retired'); load() }}>retire</button>}</td></tr>)}
        </tbody></table>
        {open && <div className="log" style={{ marginTop: 8 }}>{JSON.stringify(d.skills.find(s => s.id === open)?.steps, null, 1)}</div>}
      </div>
    </div>
    <div className="card" style={{ marginTop: 14 }}><h2>Recorded demonstrations ({d.recordings.length})</h2><p className="small muted">Captured when you drove the live browser (sign-in, or with "record" on). Distil one into a draft skill. Passwords are masked at capture time.</p>
      <table><thead><tr><th>When</th><th>Portal</th><th>Events</th><th>Sample</th><th></th></tr></thead><tbody>
        {d.recordings.map(r => <tr key={r.id}><td className="small muted">{fmt(r.created_at)}</td><td>{r.portal}</td><td>{r.events}</td><td className="mono small">{r.sample.map((e, i) => <div key={i}>{e.type} {e.target?.id || e.target?.name || e.key || ''} {e.value || ''}</div>)}</td>
          <td>{r.distilled_skill_id ? <span className="pill submitted">skill #{r.distilled_skill_id}</span> : <button className="btn sm" onClick={async () => { const x = await post(`/api/learning/recordings/${r.id}/distill`); toast(`Draft skill with ${x.steps.length} steps`); load() }}>Distil into skill</button>}</td></tr>)}
        {d.recordings.length === 0 && <tr><td colSpan={5} className="muted">No recordings yet. The first portal sign-in you do in the live view becomes one.</td></tr>}
      </tbody></table></div>
  </div>
}

import React, { useContext, useEffect, useState } from 'react'
import { Ctx } from '../App.jsx'
import { get, post, fmt } from '../api.js'
import PlanPicker from './PlanPicker.jsx'

export default function Plans() {
  const { refresh, toast } = useContext(Ctx)
  const [s, setS] = useState(null)
  const load = async () => setS(await get('/api/billing/status'))
  useEffect(() => { load() }, [])
  return <div>
    <div className="topbar"><h1>Plan &amp; billing</h1></div>
    {s && <div className="grid g4" style={{ marginBottom: 14 }}>
      <div className="card kpi"><div className="n">{s.plan ? s.plan.name : '—'}</div><div className="l">current plan{s.subscription && ` · ${s.subscription.provider}`}</div></div>
      <div className="card kpi"><div className="n">{s.used_today}{s.plan && <span className="muted" style={{ fontSize: 14 }}> / {s.plan.daily_cap}</span>}</div><div className="l">applications today</div></div>
      <div className="card kpi"><div className="n">{s.used_month}{s.plan && <span className="muted" style={{ fontSize: 14 }}> / {s.plan.monthly_cap}</span>}</div><div className="l">this month</div></div>
      <div className="card kpi"><div className="n" style={{ fontSize: 16 }}>{s.subscription?.ends_at ? fmt(s.subscription.ends_at) : '—'}</div><div className="l">renews / ends</div></div>
    </div>}
    <div className="card"><PlanPicker onDone={load} />
      {s?.subscription && <button className="btn bad sm" style={{ marginTop: 10 }} onClick={async () => { await post('/api/billing/cancel'); toast('Cancelled; the agent is paused'); await refresh(); load() }}>Cancel plan</button>}</div>
  </div>
}

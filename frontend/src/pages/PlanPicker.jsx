import React, { useContext, useEffect, useState } from 'react'
import { Ctx } from '../App.jsx'
import { get, post } from '../api.js'

export default function PlanPicker({ onDone }) {
  const { user, refresh, toast } = useContext(Ctx)
  const [plans, setPlans] = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const load = async () => { setPlans(await get('/api/billing/plans')); setStatus(await get('/api/billing/status')) }
  useEffect(() => { load() }, [])
  if (!plans) return <div>Loading…</div>
  const pay = async (id) => {
    setBusy(id); setErr('')
    try {
      if (plans.mode === 'demo') { await post('/api/billing/demo-activate', { plan: id }); toast('Plan activated (demo payment)'); await refresh(); await load(); onDone && onDone(); return }
      const o = await post('/api/billing/order', { plan: id })
      await new Promise((resolve, reject) => {
        const rz = new window.Razorpay({ key: o.key_id, amount: o.amount, currency: o.currency, name: 'AutoJopps', description: o.plan.name + ' plan (monthly)', order_id: o.order_id, prefill: o.prefill,
          theme: { color: '#0E7A66' }, handler: async (resp) => { try { await post('/api/billing/verify', resp); resolve() } catch (e) { reject(e) } }, modal: { ondismiss: () => reject(new Error('payment cancelled')) } })
        rz.open()
      })
      toast('Payment verified; plan active'); await refresh(); await load(); onDone && onDone()
    } catch (x) { setErr(x.message) } finally { setBusy('') }
  }
  return <div>
    {err && <div className="alert">{err}</div>}
    <div className="grid g3">{plans.plans.map(p => {
      const cur = status?.subscription?.plan === p.id
      return <div key={p.id} className="card" style={cur ? { borderColor: 'var(--acc)' } : {}}>
        <div className="row" style={{ justifyContent: 'space-between' }}><h3>{p.name}</h3>{cur && <span className="pill submitted">current</span>}</div>
        <div className="kpi"><div className="n">₹{p.price_inr.toLocaleString('en-IN')}<span className="muted" style={{ fontSize: 13 }}> /month</span></div></div>
        <ul className="small" style={{ paddingLeft: 18 }}><li>up to <b>{p.daily_cap}</b> applications a day</li><li>up to <b>{p.monthly_cap}</b> a month</li><li>{p.runners} apply runner{p.runners > 1 ? 's' : ''}{p.planner ? ' + planner' : ''}</li><li>human-help alerts, tracking, learning</li></ul>
        <button className="btn" disabled={!!busy} onClick={() => pay(p.id)}>{busy === p.id ? 'Working…' : cur ? 'Renew' : plans.mode === 'demo' ? 'Activate (demo)' : 'Pay with Razorpay (test)'}</button>
      </div>
    })}</div>
    <p className="small muted">Prices include 18% GST. Payment mode: <b>{plans.mode}</b>{plans.mode === 'demo' && ' (add Razorpay test keys to .env for a real checkout)'}.</p>
  </div>
}

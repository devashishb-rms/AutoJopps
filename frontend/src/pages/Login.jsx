import React, { useContext, useState } from 'react'
import { Ctx } from '../App.jsx'
import { post } from '../api.js'

export default function Login() {
  const { refresh, cfg } = useContext(Ctx)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const google = cfg?.modes?.google === 'live'
  const demo = async (e) => { e.preventDefault(); setErr(''); try { await post('/api/auth/demo', { email, name }); await refresh() } catch (x) { setErr(x.message) } }
  return (
    <div className="main" style={{ maxWidth: 980, margin: '0 auto' }}>
      <div className="hero">
        <div className="brand"><span className="dot" />AutoJopps</div>
        <h1 style={{ fontSize: 34 }}>Your job search, applied for you — with you in the loop.</h1>
        <p className="muted" style={{ maxWidth: 620 }}>Upload a resume, set your targets, pick a plan. AutoJopps finds matching roles, tailors each application, applies, and pauses for you only when a human is truly needed (OTP, a human check, or a question only you can answer). Everything is tracked.</p>
        <div className="grid g2" style={{ marginTop: 20 }}>
          <div className="card">
            <h3>Sign in with Google</h3>
            <p className="small muted">Use the same Google account you use on job portals. Your Google password is never stored.</p>
            {google ? <a className="btn" href="/api/auth/google/start" style={{ display: 'inline-block', textDecoration: 'none' }}>Continue with Google</a>
              : <button className="btn" disabled title="Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env">Continue with Google (not configured)</button>}
          </div>
          <form className="card" onSubmit={demo}>
            <h3>Demo sign-in</h3>
            <p className="small muted">For demos and local runs without a Google client. Any email works.</p>
            <label>Email</label><input value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
            <label>Name</label><input value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
            {err && <div className="alert">{err}</div>}
            <button className="btn" style={{ marginTop: 12 }}>Enter demo</button>
          </form>
        </div>
        <p className="small muted" style={{ marginTop: 16 }}>Plans: Basic ₹501/mo (5 a day, 100 a month) · Premium ₹1,001/mo (10 / 200) · Ultra ₹2,001/mo (20 / 400).</p>
      </div>
    </div>
  )
}

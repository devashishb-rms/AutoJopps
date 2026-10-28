import React, { useEffect, useState } from 'react'
import { Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { get, post } from './api.js'
import Login from './pages/Login.jsx'
import Onboarding from './pages/Onboarding.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Applications from './pages/Applications.jsx'
import Learning from './pages/Learning.jsx'
import Plans from './pages/Plans.jsx'
import Admin from './pages/Admin.jsx'
import Settings from './pages/Settings.jsx'

export const Ctx = React.createContext(null)

export default function App() {
  const [user, setUser] = useState(undefined)
  const [cfg, setCfg] = useState(null)
  const [toast, setToast] = useState('')
  const nav = useNavigate()
  const refresh = async () => { try { setUser(await get('/api/auth/me')) } catch { setUser(null) } }
  useEffect(() => { refresh(); get('/api/auth/config').then(setCfg) }, [])
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 3500); return () => clearTimeout(t) }, [toast])
  const logout = async () => { await post('/api/auth/logout'); setUser(null); nav('/') }
  if (user === undefined) return <div className="main">Loading…</div>
  const ctx = { user, refresh, cfg, toast: setToast }
  if (!user) return <Ctx.Provider value={ctx}><Routes><Route path="*" element={<Login />} /></Routes>{toast && <div className="toast">{toast}</div>}</Ctx.Provider>
  const onboarded = user.onboarding_step >= 6
  return (
    <Ctx.Provider value={ctx}>
      <div className="shell">
        <aside className="side">
          <div className="brand"><span className="dot" />AutoJopps</div>
          <NavLink to="/app">Overview</NavLink>
          <NavLink to="/app/applications">Applications</NavLink>
          <NavLink to="/app/learning">Learning</NavLink>
          <NavLink to="/app/plans">Plan &amp; billing</NavLink>
          <NavLink to="/app/settings">Profile &amp; settings</NavLink>
          <NavLink to="/app/admin">Admin (founder view)</NavLink>
          <a href="/portal/" target="_blank" rel="noreferrer">JobHub mock portal ↗</a>
          <div className="spacer" />
          {cfg && <div className="mode">google:{cfg.modes.google} · claude:{cfg.modes.claude} · pay:{cfg.modes.razorpay}</div>}
          <div className="who">{user.name || user.email}<br /><a href="#" onClick={e => { e.preventDefault(); logout() }}>Sign out</a></div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<Navigate to="/app" />} />
            <Route path="/app" element={onboarded ? <Dashboard /> : <Navigate to="/app/onboarding" />} />
            <Route path="/app/onboarding" element={<Onboarding />} />
            <Route path="/app/applications" element={<Applications />} />
            <Route path="/app/learning" element={<Learning />} />
            <Route path="/app/plans" element={<Plans />} />
            <Route path="/app/settings" element={<Settings />} />
            <Route path="/app/admin" element={<Admin />} />
            <Route path="*" element={<Navigate to="/app" />} />
          </Routes>
        </main>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </Ctx.Provider>
  )
}

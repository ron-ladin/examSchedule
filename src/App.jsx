import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import LandingPage from './components/LandingPage'
import Login from './components/Login'
import Register from './components/Register'
import Dashboard from './components/Dashboard'
import ProcessingState from './components/ProcessingState'
import ResultsView from './components/ResultsView'
import DetailedCalendar from './components/DetailedCalendar'

function DarkInit() {
  useEffect(() => {
    document.documentElement.classList.add('dark')
    document.body.style.background = '#0b1326'
    document.body.style.color = '#dae2fd'
  }, [])
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <DarkInit />
      <Routes>
        <Route path="/"           element={<LandingPage />} />
        <Route path="/login"      element={<Login />} />
        <Route path="/register"   element={<Register />} />
        <Route path="/dashboard"  element={<Dashboard />} />
        <Route path="/processing" element={<ProcessingState />} />
        <Route path="/results"    element={<ResultsView />} />
        <Route path="/calendar"   element={<DetailedCalendar />} />
        <Route path="*"           element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

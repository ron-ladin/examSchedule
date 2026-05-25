import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import Login from './components/Login'
import Register from './components/Register'
import Dashboard from './components/Dashboard'
import ProcessingState from './components/ProcessingState'
import ResultsView from './components/ResultsView'
import DetailedCalendar from './components/DetailedCalendar'

export default function App() {
  return (
    <BrowserRouter>
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

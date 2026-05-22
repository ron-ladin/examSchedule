import { BrowserRouter, Routes, Route } from 'react-router-dom'

// Screens — to be implemented by Niv (SCRUM-80–94)
function InputScreen()  { return <div>Input Screen — SCRUM-82–88</div> }
function OutputScreen() { return <div>Output Screen — SCRUM-89–94</div> }

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"        element={<InputScreen />} />
        <Route path="/output"  element={<OutputScreen />} />
      </Routes>
    </BrowserRouter>
  )
}

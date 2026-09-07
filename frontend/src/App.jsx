import { useState } from 'react'
import LandingPage from './LandingPage'
import MapView from './MapView'
import './App.css'

function App() {
  const [entered, setEntered] = useState(false)

  if (!entered) {
    return <LandingPage onEnter={() => setEntered(true)} />
  }

  return <MapView />
}

export default App
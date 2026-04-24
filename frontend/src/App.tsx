import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [status, setStatus] = useState<string>('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('offline'))
  }, [])

  return (
    <div className="app">
      <h1>Tawthiq</h1>
      <p>Document Validation System</p>
      <p className="status">
        API Status: <span className={status === 'ok' ? 'online' : 'offline'}>{status}</span>
      </p>
    </div>
  )
}

export default App

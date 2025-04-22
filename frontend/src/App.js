import React, { useState, useEffect } from 'react';
import CrimeCard from './components/CrimeCard';
import './styles/App.css';

function App() {
  const [crimes, setCrimes] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/crimes')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(json => {
        if (json.error) throw new Error(json.error);
        setCrimes(json.data);
      })
      .catch(err => {
        console.error(err);
        setCrimes([]);           // empty array   → “No crimes found”
      })
      .finally(() => setLoading(false));  // always turn spinner off
  }, []);
  

  return (
    <div className="App">
      <header className="header">
        <h1>Berkeley Crime Feed</h1>
        <p>Community-reported safety alerts</p>
      </header>
      
      <main className="crime-feed">
        {loading ? (
            <p>Loading crimes...</p>             // ←  “spinner” placeholder
        ) : crimes.length === 0 ? (
            <p>No crimes found or API error.</p>
        ) : (
            crimes.map(crime => (
                <CrimeCard key={crime.OBJECTID} crime={crime} />
            ))
        )}



      </main>
    </div>
  );
}

export default App;
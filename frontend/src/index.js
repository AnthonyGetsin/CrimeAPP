import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/App.css'; // Global styles

// Berkeley-themed loading component
const Loading = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    backgroundColor: '#003262' // Berkeley blue
  }}>
    <h1 style={{ color: '#FDB515' }}>Loading Crime Data...</h1> {/* Berkeley gold */}
  </div>
);

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    {/* Show loading state until app mounts */}
    <React.Suspense fallback={<Loading />}>
      <App />
    </React.Suspense>
  </React.StrictMode>
);
import React from 'react';
import { FaShieldAlt } from 'react-icons/fa';

export default function Header() {
  return (
    <header className="app-header">
      <div className="header-content">
        <FaShieldAlt className="logo" />
        <h1>Berkeley Crime Alerts</h1>
      </div>
      <nav>
        <button className="nav-btn">Map View</button>
        <button className="nav-btn">Report</button>
      </nav>
    </header>
  );
}
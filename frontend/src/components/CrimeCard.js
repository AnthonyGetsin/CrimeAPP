import React from 'react';
import { FaMapMarkerAlt, FaClock, FaArrowUp, FaComment } from 'react-icons/fa';
import '../styles/CrimeCard.css';

export default function CrimeCard({ crime }) {
  return (
    <div className="crime-card">
      <div className="vote-buttons">
        <button className="upvote"><FaArrowUp /></button>
        <span>{crime.OBJECTID % 100}</span> {/* Temporary "score" */}
      </div>
      
      <div className="crime-content">
        <h3>{crime.Incident_Type}</h3>
        <p className="crime-meta">
          <span><FaClock /> {new Date(crime.Occurred_Datetime).toLocaleString()}</span>
          <span><FaMapMarkerAlt /> {crime.Block_Address}</span>
        </p>
        <div className="crime-description">
          <p>Case #{crime.Case_Number}</p>
          {crime.DESCRIPTION && <p>{crime.DESCRIPTION}</p>}
        </div>
        
        <div className="crime-footer">
          <button className="comments-btn">
            <FaComment /> Discuss ({(crime.OBJECTID % 5) + 1})
          </button>
        </div>
      </div>
    </div>
  )
}
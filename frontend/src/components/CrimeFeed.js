import React from 'react';
import CrimeCard from './CrimeCard';

export default function CrimeFeed({ crimes }) {
  return (
    <div className="crime-feed">
      {crimes.map(crime => (
        <CrimeCard 
          key={crime.OBJECTID} 
          crime={crime} 
        />
      ))}
    </div>
  );
}
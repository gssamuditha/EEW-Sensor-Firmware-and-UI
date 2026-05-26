import { createContext, useState, useEffect, useContext } from 'react';

export const TIMEZONES = [
  "UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo", "Asia/Colombo", "Pacific/Auckland"
];

const TimeZoneContext = createContext();

export function TimeZoneProvider({ children }) {
  const [timeZone, setTimeZone] = useState(() => {
    return localStorage.getItem('eew_timezone') || 'UTC';
  });

  useEffect(() => {
    localStorage.setItem('eew_timezone', timeZone);
  }, [timeZone]);

  return (
    <TimeZoneContext.Provider value={{ timeZone, setTimeZone, TIMEZONES }}>
      {children}
    </TimeZoneContext.Provider>
  );
}

export function useTimeZone() {
  return useContext(TimeZoneContext);
}

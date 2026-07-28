import { createContext, useState, useEffect, useContext } from 'react';

export const TIMEZONES = [
  "UTC",
  "America/Anchorage",
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Kyiv",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Dhaka",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Pacific/Auckland",
  "Pacific/Honolulu"
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

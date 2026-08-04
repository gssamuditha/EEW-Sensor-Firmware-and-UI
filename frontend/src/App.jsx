import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './views/Dashboard';
import Export from './views/Export';
import Analysis from './views/Analysis';
import Settings from './views/Settings';
import Expanded from './views/Expanded';
import Setup from './views/Setup';
import { TimeZoneProvider } from './TimeZoneContext';
import { ThemeProvider } from './ThemeContext';

import TourGuide from './components/TourGuide';

function App() {
  const [isConfigured, setIsConfigured] = useState(null);

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => setIsConfigured(data.is_configured !== false))
      .catch(err => setIsConfigured(true));
  }, []);

  if (isConfigured === null) {
    return <div className="h-screen w-screen flex items-center justify-center bg-gray-100 dark:bg-slate-900 text-gray-500">Loading...</div>;
  }

  if (!isConfigured) {
    return (
      <ThemeProvider>
        <TimeZoneProvider>
          <Setup onComplete={() => setIsConfigured(true)} />
        </TimeZoneProvider>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <TimeZoneProvider>
        <Router>
          <TourGuide />
          <Routes>
            <Route path="/expanded" element={<Expanded />} />
            <Route path="/*" element={
              <Layout>
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/export" element={<Export />} />
                  <Route path="/analysis" element={<Analysis />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </Layout>
            } />
          </Routes>
        </Router>
      </TimeZoneProvider>
    </ThemeProvider>
  );
}

export default App;

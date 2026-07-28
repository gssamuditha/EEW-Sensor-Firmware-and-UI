import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './views/Dashboard';
import Export from './views/Export';
import Analysis from './views/Analysis';
import Settings from './views/Settings';
import Expanded from './views/Expanded';
import { TimeZoneProvider } from './TimeZoneContext';
import { ThemeProvider } from './ThemeContext';

function App() {
  return (
    <ThemeProvider>
      <TimeZoneProvider>
        <Router>
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

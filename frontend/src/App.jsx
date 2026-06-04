import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './views/Dashboard';
import Export from './views/Export';
// import Analysis from './views/Analysis'; // Hidden for version 3
import Settings from './views/Settings';
import Expanded from './views/Expanded';
import { TimeZoneProvider } from './TimeZoneContext';

function App() {
  return (
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
                {/* <Route path="/analysis" element={<Analysis />} /> */}
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Layout>
          } />
        </Routes>
      </Router>
    </TimeZoneProvider>
  );
}

export default App;

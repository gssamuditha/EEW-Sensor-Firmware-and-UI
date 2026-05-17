import { Link, useLocation } from 'react-router-dom';
import { Activity, Download, ActivitySquare, Settings } from 'lucide-react';

export default function Sidebar() {
  const location = useLocation();

  const links = [
    { name: 'Dashboard', path: '/dashboard', icon: <Activity size={20} /> },
    { name: 'Data Export', path: '/export', icon: <Download size={20} /> },
    { name: 'Analysis', path: '/analysis', icon: <ActivitySquare size={20} /> },
    { name: 'Settings', path: '/settings', icon: <Settings size={20} /> },
  ];

  return (
    <div className="w-64 h-screen bg-primary text-white flex flex-col font-sans">
      <div className="p-6 border-b border-white/10">
        <h1 className="text-xl font-bold tracking-wider">EEW SENSOR</h1>
        <p className="text-xs text-white/50 mt-1 uppercase tracking-widest">Control Panel</p>
      </div>
      <nav className="flex-1 px-4 py-6 space-y-2">
        {links.map((link) => {
          const isActive = location.pathname.startsWith(link.path);
          return (
            <Link
              key={link.name}
              to={link.path}
              className={`flex items-center space-x-3 px-4 py-3 rounded-none transition-colors ${
                isActive ? 'bg-white/10 text-white' : 'text-white/70 hover:bg-white/5 hover:text-white'
              }`}
            >
              {link.icon}
              <span className="font-medium tracking-wide">{link.name}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-white/10 text-xs text-white/40 text-center">
        SYSTEM STATUS: ONLINE
      </div>
    </div>
  );
}

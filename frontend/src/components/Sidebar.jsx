import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Activity, Download, ActivitySquare, Settings, ChevronLeft, ChevronRight } from 'lucide-react';

export default function Sidebar() {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const links = [
    { name: 'Dashboard', path: '/dashboard', icon: <Activity size={20} /> },
    { name: 'Data Export', path: '/export', icon: <Download size={20} /> },
    { name: 'Analysis', path: '/analysis', icon: <ActivitySquare size={20} /> },
    { name: 'Settings', path: '/settings', icon: <Settings size={20} /> },
  ];

  return (
    <div className={`h-screen bg-primary dark:bg-slate-950 text-white flex flex-col font-sans transition-all duration-300 ease-in-out relative shrink-0 ${isCollapsed ? 'w-[72px]' : 'w-64'}`}>
      <div className={`p-6 border-b border-white/10 flex items-center h-24 shrink-0 transition-all duration-300 ${isCollapsed ? 'justify-center px-2' : 'space-x-4'}`}>
        <img src="/logo1.png" alt="Logo" className="h-10 w-10 object-contain shrink-0" onError={(e) => e.target.style.display = 'none'} />
        <div className={`transition-all duration-300 overflow-hidden ${isCollapsed ? 'opacity-0 w-0' : 'opacity-100 w-auto'}`}>
          <h1 className="text-xl font-bold tracking-wider leading-tight whitespace-nowrap">CRISISLab</h1>
          <p className="text-[10px] text-white/50 uppercase tracking-widest mt-1 whitespace-nowrap">Network</p>
        </div>
      </div>
      <nav className="flex-1 px-3 py-6 space-y-2 overflow-x-hidden">
        {links.map((link) => {
          const isActive = location.pathname.startsWith(link.path);
          return (
            <Link
              key={link.name}
              to={link.path}
              title={isCollapsed ? link.name : undefined}
              className={`flex items-center rounded-xl transition-all duration-300 ${isActive ? 'bg-white/10 text-white' : 'text-white/70 hover:bg-white/5 hover:text-white'} ${isCollapsed ? 'justify-center p-3' : 'px-4 py-3 space-x-4'}`}
            >
              <div className="shrink-0">{link.icon}</div>
              <span className={`font-medium tracking-wide whitespace-nowrap transition-all duration-300 overflow-hidden ${isCollapsed ? 'opacity-0 w-0' : 'opacity-100'}`}>
                {link.name}
              </span>
            </Link>
          );
        })}
      </nav>
      <div className={`p-4 border-t border-white/10 text-xs text-white/40 flex items-center transition-all duration-300 overflow-hidden ${isCollapsed ? 'justify-center' : 'justify-between'}`}>
        <span className={`whitespace-nowrap transition-all duration-300 overflow-hidden ${isCollapsed ? 'opacity-0 w-0' : 'opacity-100'}`}>
          STATUS: ONLINE
        </span>
        <button 
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="text-white/50 hover:text-white p-1 rounded-md hover:bg-white/10 transition-colors shrink-0"
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {isCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
        </button>
      </div>
    </div>
  );
}

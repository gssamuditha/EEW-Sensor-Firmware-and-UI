import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ListBulletIcon, Squares2X2Icon as DashboardIcon, CircleStackIcon as DatabaseIcon, Cog8ToothIcon as Settings } from '@heroicons/react/24/solid';

const WaveformCircleIcon = ({ className }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs>
      <mask id="waveform-circle-mask">
        <rect width="24" height="24" fill="white" />
        <path d="M 3 12 h 3.5 l 1.5 -2.5 l 1.5 4 l 2.5 -8 l 2.5 10 l 2 -3.5 h 4.5" stroke="black" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </mask>
    </defs>
    <circle cx="12" cy="12" r="10" fill="currentColor" mask="url(#waveform-circle-mask)" />
  </svg>
);

export default function Sidebar() {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const links = [
    { name: 'Dashboard', path: '/dashboard', icon: <DashboardIcon className="w-5 h-5" /> },
    { name: 'Data Export', path: '/export', icon: <DatabaseIcon className="w-5 h-5" /> },
    { name: 'Analysis', path: '/analysis', icon: <WaveformCircleIcon className="w-5 h-5" /> },
    { name: 'Settings', path: '/settings', icon: <Settings className="w-5 h-5" /> },
  ];

  return (
    <div className={`
      bg-primary dark:bg-slate-950 text-white font-sans transition-all duration-300 ease-in-out relative shrink-0
      flex flex-row md:flex-col w-full h-16 md:h-screen z-50
      ${isCollapsed ? 'md:w-[72px]' : 'md:w-64'}
    `}>
      <div className={`hidden md:flex p-6 border-b border-white/10 items-center h-24 shrink-0 transition-all duration-300 ${isCollapsed ? 'justify-center px-2' : 'space-x-4'}`}>
        <img src="/logo1.png" alt="Logo" className="h-10 w-10 object-contain shrink-0" onError={(e) => e.target.style.display = 'none'} />
        <div className={`transition-all duration-300 overflow-hidden ${isCollapsed ? 'opacity-0 w-0' : 'opacity-100 w-auto'}`}>
          <h1 className="text-xl font-bold tracking-wider leading-tight whitespace-nowrap">CRISiSLab</h1>
          <p className="text-[10px] text-white/50 uppercase tracking-widest mt-1 whitespace-nowrap">Network</p>
        </div>
      </div>
      <div className="hidden md:flex pt-4 pb-4 mb-2 border-b border-white/10 justify-start pl-[18px]">
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="text-white/50 hover:text-white p-2 rounded-md hover:bg-white/10 transition-colors shrink-0"
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          <ListBulletIcon className="w-6 h-6" />
        </button>
      </div>
      <nav className="tour-sidebar flex-1 flex flex-row md:flex-col justify-around md:justify-start items-center md:items-stretch px-2 md:px-3 py-0 md:py-2 space-x-0 md:space-x-0 md:space-y-2 overflow-x-auto md:overflow-x-hidden">
        {links.map((link) => {
          const isActive = location.pathname.startsWith(link.path);
          return (
            <Link
              key={link.name}
              to={link.path}
              title={isCollapsed ? link.name : undefined}
              className={`tour-nav-${link.path.substring(1)} flex flex-col md:flex-row items-center justify-center md:justify-start rounded-xl transition-all duration-300 ${isActive ? 'bg-white/10 text-white dark:bg-amber-500/10 dark:text-amber-500' : 'text-white/70 hover:bg-white/5 hover:text-white hover:dark:text-amber-400'} 
              p-2 md:p-3 ${isCollapsed ? 'md:justify-center' : 'md:px-4 md:space-x-4'} gap-1 md:gap-0 h-14 md:h-auto min-w-[64px]`}
            >
              <div className="shrink-0">{link.icon}</div>
              <span className={`text-[10px] md:text-base font-medium tracking-wide whitespace-nowrap transition-all duration-300 overflow-hidden ${isCollapsed ? 'md:opacity-0 md:w-0' : 'opacity-100'} block md:inline`}>
                {link.name}
              </span>
            </Link>
          );
        })}
      </nav>
      <div className="hidden md:flex p-4 border-t border-white/10 text-xs text-white/40 items-center justify-center transition-all duration-300 overflow-hidden">
        <span className={`whitespace-nowrap transition-all duration-300 overflow-hidden ${isCollapsed ? 'opacity-0 w-0' : 'opacity-100'}`}>
          STATUS: ONLINE
        </span>
      </div>
    </div>
  );
}

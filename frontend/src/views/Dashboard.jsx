import { useState, useEffect, useCallback } from 'react';
import LiveChart from '../components/LiveChart';
import { useTimeZone } from '../TimeZoneContext';
import { ServerStackIcon, ChartBarIcon } from '@heroicons/react/24/solid';

export default function Dashboard() {
  const { timeZone, setTimeZone, TIMEZONES } = useTimeZone();

  const [sps, setSps] = useState(0);
  const [clientSps, setClientSps] = useState(0);
  const [activeChannels, setActiveChannels] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [sensorSettings, setSensorSettings] = useState({ latitude: 0.0, longitude: 0.0, elevation: 0.0, device_name: 'Loading...' });

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const [systemStats, setSystemStats] = useState({
    cpu_percent: 0,
    disk_percent: 0,
    uptime: '-',
    local_ip: '-',
    mac_address: '-',
    internet_status: false,
    server_status: false,
    hardware_sps: 0,
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const protocol = window.location.protocol;
        const host = window.location.host;
        const res = await fetch(`${protocol}//${host}/api/system_status`);
        const data = await res.json();
        if (!data.error) {
          setSystemStats(data);
        }
      } catch (e) {
        console.error("Failed to fetch system stats");
      }
    };
    fetchStats();
    const int = setInterval(fetchStats, 5000);
    return () => clearInterval(int);
  }, []);

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        setSensorSettings({
          latitude: data.latitude || 0.0,
          longitude: data.longitude || 0.0,
          elevation: data.elevation || 0.0,
          device_name: data.device_name || 'CRISIS-NODE-01'
        });
      })
      .catch(console.error);
  }, []);

  const updateSps = useCallback((val) => {
    setSps(val);
  }, []);

  const handleClientSps = useCallback((val) => {
    setClientSps(val);
  }, []);

  const handleChannelsFound = useCallback((channels) => {
    setActiveChannels(channels);
  }, []);

  return (
    <div className="p-6 h-full flex flex-col bg-slate-50 dark:bg-slate-900 overflow-hidden">
      <div className="flex justify-between items-center mb-4 flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 mr-2">
            <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 tracking-wider">Eew Sensor</h1>
            <span className="text-slate-300 dark:text-slate-700 text-xl">|</span>
          </div>
          <h2 className="text-xl font-bold text-primary dark:text-sky-400 tracking-wide">Live Telemetry</h2>
          {/* Sensor-side (hardware) SPS */}
          <div className="py-1 text-slate-500 dark:text-slate-400 text-xs font-bold flex items-center space-x-2 ml-2">
            <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
            <span>Sensor {systemStats.avg_sps} sps</span>
          </div>
          {/* Client-side (browser) SPS */}
          <div className="py-1 text-slate-500 dark:text-slate-400 text-xs font-bold flex items-center space-x-2 ml-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span>Client {clientSps} sps</span>
          </div>
        </div>
        <div className="flex items-center space-x-3 text-sm">
          <div className="font-mono font-semibold text-slate-600 dark:text-slate-200 mr-4 bg-slate-100 dark:bg-slate-700 px-3 py-1.5 rounded-md border-0 shadow-sm">
            {new Intl.DateTimeFormat('en-US', {
              timeZone: timeZone,
              year: 'numeric', month: 'short', day: 'numeric',
              hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
            }).format(currentTime)}
          </div>
          <label className="font-bold text-slate-500 dark:text-slate-300 tracking-wider">Timezone</label>
          <select
            value={timeZone}
            onChange={(e) => setTimeZone(e.target.value)}
            className="border-0 rounded-md px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-300 font-mono text-sm bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-200 shadow-sm font-semibold cursor-pointer"
          >
            {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-4 gap-6">

        {/* Left Column: Widget 1 */}
        <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-5 shadow-md flex flex-col justify-between">
          <div>
            <div className="text-[13px] font-bold text-slate-400 dark:text-slate-200 tracking-widest mb-4">Device Details</div>
            <div className="space-y-3 font-mono text-sm">
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Name</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{sensorSettings.device_name}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Model</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">Eew-Pi-4</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Channels</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{activeChannels.join(', ') || '-'}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Local IP</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{systemStats.local_ip}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Mac Addr</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{systemStats.mac_address}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Latitude</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{sensorSettings.latitude.toFixed(5)}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Longitude</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{sensorSettings.longitude.toFixed(5)}</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Elevation</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{sensorSettings.elevation.toFixed(1)} m</span>
              </div>
              <div className="grid grid-cols-3 items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Uptime</span>
                <span className="text-primary dark:text-slate-100 font-bold col-span-2">{systemStats.uptime}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Middle Column: Widget 3 */}
        <div className="col-span-2 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md flex flex-col min-h-0 overflow-hidden">
          <LiveChart timeZone={timeZone} updateSps={updateSps} onClientSps={handleClientSps} onChannelsFound={handleChannelsFound} />
        </div>

        {/* Right Column */}
        <div className="flex flex-col gap-6 min-h-0 overflow-y-auto pr-1">

          {/* Widget 2: Network & Connections */}
          <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-5 shadow-md shrink-0">
            <div className="text-[13px] font-bold text-slate-400 dark:text-slate-200 tracking-widest mb-4">Network</div>
            <div className="space-y-3 font-mono text-sm">
              <div className="flex justify-between items-center border-b border-slate-50 dark:border-slate-700/50 pb-2">
                <span className="font-bold text-slate-400">Internet</span>
                <div className="flex items-center space-x-2">
                  <span className={`w-2 h-2 rounded-full ${systemStats.internet_status ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                  <span className={systemStats.internet_status ? 'text-emerald-500 font-bold' : 'text-red-500 font-bold'}>
                    {systemStats.internet_status ? 'Online' : 'Offline'}
                  </span>
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="font-bold text-slate-400">Server</span>
                <div className="flex items-center space-x-2">
                  <span className={`w-2 h-2 rounded-full ${systemStats.server_status ? 'bg-emerald-500' : 'bg-red-500'}`}></span>
                  <span className={systemStats.server_status ? 'text-emerald-500 font-bold' : 'text-red-500 font-bold'}>
                    {systemStats.server_status ? 'Active' : 'Down'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Widget 4: System Status */}
          <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-5 shadow-md shrink-0">
            <div className="text-[13px] font-bold text-slate-400 dark:text-slate-200 tracking-widest mb-4">System Status</div>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs font-bold font-mono text-slate-400 mb-1">
                  <span>Cpu Usage</span>
                  <span>{systemStats.cpu_percent.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5">
                  <div className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${systemStats.cpu_percent}%` }}></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs font-bold font-mono text-slate-400 mb-1">
                  <span>Disk Usage</span>
                  <span>{systemStats.disk_percent.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-1.5">
                  <div className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${systemStats.disk_percent}%` }}></div>
                </div>
              </div>
            </div>
          </div>

          {/* Widget 6: Server Actions */}
          <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-5 shadow-md flex-1 flex flex-col shrink-0">
            <div className="text-[13px] font-bold text-slate-400 dark:text-slate-200 tracking-widest mb-4">Server Actions</div>
            <div className="flex flex-col gap-3 h-full">
              <a href="#station" className="flex items-center justify-center border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg p-3 hover:bg-slate-50 transition-all shadow-md hover:shadow-lg text-slate-600 dark:text-slate-200 hover:text-primary hover:dark:text-amber-400 cursor-pointer">
                <ServerStackIcon className="w-5 h-5 mr-2 shrink-0" />
                <span className="text-xs font-bold">Station View</span>
              </a>
              <a href="#data" className="flex items-center justify-center border border-slate-200 dark:border-slate-600 dark:bg-slate-700 rounded-lg p-3 hover:bg-slate-50 transition-all shadow-md hover:shadow-lg text-slate-600 dark:text-slate-200 hover:text-primary hover:dark:text-amber-400 cursor-pointer">
                <ChartBarIcon className="w-5 h-5 mr-2 shrink-0" />
                <span className="text-xs font-bold">Data View</span>
              </a>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { Save, Plus, X, Wifi, Power, MapPin, Target, Monitor, Settings as SettingsIcon, Activity, Eye, EyeOff, Loader2, Trash2, Sun, Moon, Palette } from 'lucide-react';
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});
import { useTheme } from '../ThemeContext';

function LocationMarker({ position, setPosition }) {
  useMapEvents({
    click(e) {
      setPosition(e.latlng);
    },
  });

  return position === null ? null : (
    <Marker position={position}></Marker>
  );
}

export default function Settings() {
  const { theme, toggleTheme } = useTheme();
  const [targets, setTargets] = useState([{ name: 'Main Server', ip: '127.0.0.1', port: 2098, format: 'corrected' }]);
  const [newName, setNewName] = useState('');
  const [newIp, setNewIp] = useState('');
  const [newPort, setNewPort] = useState(2098);
  const [newFormat, setNewFormat] = useState('corrected');
  const [lat, setLat] = useState(0.0);
  const [lon, setLon] = useState(0.0);
  const [deviceName, setDeviceName] = useState('CRISIS-NODE-01');
  const [deviceId, setDeviceId] = useState('T0021');
  const [calibrationTime, setCalibrationTime] = useState(60);
  const [retentionDays, setRetentionDays] = useState(7);
  const [archiveSize, setArchiveSize] = useState(0);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  
  const [dataForwarding, setDataForwarding] = useState(true);
  const [activeWifi, setActiveWifi] = useState(null);
  const [savedNetworks, setSavedNetworks] = useState([]);
  const [wifiLoading, setWifiLoading] = useState(false);
  const [switchModal, setSwitchModal] = useState(null); // null or { ssid: string }

  const [status, setStatus] = useState(null);
  const [wifiStatus, setWifiStatus] = useState(null);
  const [isRestartModalOpen, setIsRestartModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('general');

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.targets && data.targets.length > 0) setTargets(data.targets);
        setLat(data.latitude || 0.0);
        setLon(data.longitude || 0.0);
        if (data.device_name) setDeviceName(data.device_name);
        if (data.device_id) setDeviceId(data.device_id);
        if (data.calibration_time) setCalibrationTime(data.calibration_time);
        if (data.retention_days !== undefined) setRetentionDays(data.retention_days);
        if (data.archive_size_bytes !== undefined) setArchiveSize(data.archive_size_bytes);
        if (data.active_wifi) setActiveWifi(data.active_wifi);
        if (data.data_forwarding !== undefined) setDataForwarding(data.data_forwarding);
      })
      .catch(console.error);

    fetch('/api/wifi/networks')
      .then(res => res.json())
      .then(data => {
        if (data.networks) setSavedNetworks(data.networks);
        if (data.active_ssid) setActiveWifi(data.active_ssid);
      })
      .catch(console.error);
  }, []);

  const showStatus = (msg, isError = false) => {
    setStatus({ msg, isError });
    setTimeout(() => setStatus(''), 3000);
  };

  const showWifiStatus = (msg, isError = false) => {
    setWifiStatus({ msg, isError });
    setTimeout(() => setWifiStatus(''), 5000);
  };

  const handleAddTarget = () => {
    if (!newIp || !newName) return;
    setTargets([...targets, { name: newName, ip: newIp, port: parseInt(newPort), format: newFormat }]);
    setNewName('');
    setNewIp('');
    setNewFormat('corrected');
  };

  const handleToggleFormat = (index) => {
    setTargets(targets.map((t, i) =>
      i === index ? { ...t, format: t.format === 'corrected' ? 'raw' : 'corrected' } : t
    ));
  };

  const handleRemoveTarget = (index) => {
    setTargets(targets.filter((_, i) => i !== index));
  };

  const handleSaveSettings = async () => {
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          targets,
          latitude: parseFloat(lat),
          longitude: parseFloat(lon),
          device_name: deviceName,
          device_id: deviceId,
          calibration_time: parseInt(calibrationTime),
          retention_days: parseInt(retentionDays),
          data_forwarding: dataForwarding
        })
      });
      if (res.ok) {
        showStatus('Configuration saved successfully.');
      } else {
        showStatus('Error saving configuration.', true);
      }
    } catch (e) {
      console.error(e);
      showStatus('Error saving configuration.', true);
    }
  };

  const handleWifiConnect = async () => {
    if (!ssid) { showWifiStatus('SSID is required.', true); return; }
    if (!password) { showWifiStatus('Password is required.', true); return; }
    
    setWifiLoading(true);
    showWifiStatus('Saving and connecting...');
    try {
      const res = await fetch('/api/wifi/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        // Backend accepted — it will switch networks in ~3 seconds
        setSwitchModal({ ssid });
      } else {
        showWifiStatus('Failed: ' + data.message, true);
      }
    } catch (e) {
      console.error(e);
      showWifiStatus('Network error during Wi-Fi connect.', true);
    } finally {
      setWifiLoading(false);
    }
  };

  const handleConnectSaved = async (targetSsid) => {
    setWifiLoading(true);
    showWifiStatus(`Switching to ${targetSsid}...`);
    try {
      const res = await fetch('/api/wifi/connect_saved', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid: targetSsid })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        // Backend accepted — it will switch networks in ~3 seconds
        setSwitchModal({ ssid: targetSsid });
      } else {
        showWifiStatus('Failed: ' + data.message, true);
      }
    } catch (e) {
      console.error(e);
      showWifiStatus('Network error during Wi-Fi connect.', true);
    } finally {
      setWifiLoading(false);
    }
  };

  const handleForgetNetwork = async (targetSsid) => {
    try {
      const res = await fetch('/api/wifi/forget', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid: targetSsid })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setSavedNetworks(prev => prev.filter(n => n.ssid !== targetSsid));
        if (activeWifi === targetSsid) setActiveWifi(null);
        showWifiStatus(`"${targetSsid}" has been forgotten.`);
      } else {
        showWifiStatus('Failed: ' + data.message, true);
      }
    } catch (e) {
      console.error(e);
      showWifiStatus('Failed to forget network.', true);
    }
  };

  const handleRestartConfirm = async () => {
    setIsRestartModalOpen(false);
    try {
      await fetch('/api/system/restart', { method: 'POST' });
      showStatus('System is restarting...');
    } catch (e) {
      console.error(e);
      showStatus('Failed to trigger restart.', true);
    }
  };

  const tabs = [
    { id: 'general', label: 'General' },
    { id: 'network', label: 'Network' },
    { id: 'system', label: 'System' }
  ];

  return (
    <div className="p-6 h-full bg-gray-50 dark:bg-slate-900 flex flex-col w-full overflow-hidden">
      
      <div className="w-full flex justify-between items-center mb-4 shrink-0">
        <h2 className="text-2xl font-bold text-primary dark:text-blue-400 tracking-wide uppercase">System Configuration</h2>
        {status && (
          <div className={`px-4 py-2 text-sm font-bold font-mono shadow-sm ${status.isError ? 'bg-red-50 text-red-600 border border-red-200' : 'bg-green-50 text-green-600 border border-green-200'}`}>
            {status.msg}
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="w-full border-b border-gray-200 dark:border-slate-700 mb-6 shrink-0">
        <ul className="flex flex-wrap -mb-px text-sm font-bold text-center">
          {tabs.map(tab => (
            <li className="mr-8" key={tab.id}>
              <button
                onClick={() => setActiveTab(tab.id)}
                className={`inline-block py-3 border-b-2 transition-all duration-200 ${
                  activeTab === tab.id 
                    ? 'text-[#1a4162] border-[#1a4162]' 
                    : 'text-gray-400 dark:text-slate-500 border-transparent hover:text-gray-600 dark:text-slate-300 hover:border-gray-300 dark:border-slate-600'
                }`}
              >
                {tab.label}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Tab Content Container */}
      <div className="w-full flex-1 relative min-h-0">
        
        {/* Tab 1: General */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'general' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-2 gap-6 h-full">
            
            {/* Left column: Device Details + Response File */}
            <div className="flex flex-col gap-6 overflow-y-auto">

              {/* Widget 1: Device Details */}
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col">
                <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                  <Monitor size={16} className="mr-2" /> Device Details
                </h3>
                <div className="flex-1 flex flex-col space-y-4">
                  <div>
                    <label className="block text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Device Name</label>
                    <input 
                      type="text" 
                      value={deviceName}
                      onChange={e => setDeviceName(e.target.value)}
                      placeholder="CRISIS-NODE-01"
                      className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm mb-3"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Device ID (5 chars)</label>
                    <input 
                      type="text" 
                      value={deviceId}
                      onChange={e => setDeviceId(e.target.value)}
                      maxLength={5}
                      placeholder="T0021"
                      className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                    <p className="text-xs text-gray-400 dark:text-slate-500 font-mono mt-1">Used for SEED station code (e.g. T0021)</p>
                  </div>

                  <div className="flex justify-end pt-4 border-t border-gray-100 dark:border-slate-700">
                    <button 
                      onClick={handleSaveSettings}
                      className="bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                    >
                      <Save size={16} />
                      <span>Save Name</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Widget 2: Device Response File */}
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col">
                <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                  <Activity size={16} className="mr-2" /> Device Response File
                </h3>
                <div className="space-y-3">
                  <p className="text-xs text-gray-500 dark:text-slate-400 font-mono leading-relaxed">
                    Download the <strong>StationXML</strong> instrument response file for this sensor. 
                    Required when a UDP target is set to <strong>Raw Counts</strong> mode — the receiving 
                    server uses this file to convert raw 24-bit ADC counts back to m/s².
                  </p>
                  <a
                    href="/api/metadata/stationxml"
                    download
                    className="w-full bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity text-center"
                  >
                    <Save size={16} />
                    <span>Download StationXML</span>
                  </a>
                </div>
              </div>

            </div>{/* end left column */}

            {/* Widget 3: Device Location — right column full height */}
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-full min-h-0">
              <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                <MapPin size={16} className="mr-2" /> Device Location
              </h3>
              <div className="flex-1 flex flex-col min-h-0">
                <div className="flex-1 min-h-0 mb-4 border border-gray-200 dark:border-slate-700 z-0 relative">
                  <MapContainer center={[lat || 0, lon || 0]} zoom={2} scrollWheelZoom={true} style={{ height: '100%', width: '100%' }}>
                    <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                    <LocationMarker position={{lat, lng: lon}} setPosition={(pos) => { setLat(pos.lat); setLon(pos.lng); }} />
                  </MapContainer>
                </div>
                <div className="grid grid-cols-2 gap-4 shrink-0 mb-4">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-1">Latitude</label>
                    <input 
                      type="number" step="any"
                      value={lat}
                      onChange={e => setLat(parseFloat(e.target.value) || 0)}
                      className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-1">Longitude</label>
                    <input 
                      type="number" step="any"
                      value={lon}
                      onChange={e => setLon(parseFloat(e.target.value) || 0)}
                      className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-4 border-t border-gray-100 dark:border-slate-700 shrink-0">
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                  >
                    <Save size={16} />
                    <span>Save Location</span>
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Tab 2: Network */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'network' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-2 gap-6 h-full">
            
            {/* Widget 1: Wi-Fi Manager */}
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                <Wifi size={16} className="mr-2" /> Wi-Fi Configuration
              </h3>
              <div className="space-y-4">
                
                {/* Active Connection Indicator */}
                <div className="flex items-center space-x-2 bg-blue-50 border border-blue-100 px-4 py-2">
                  <div className={`w-2 h-2 rounded-full ${activeWifi ? 'bg-green-500' : 'bg-gray-400'}`}></div>
                  <span className="text-xs font-bold text-[#1a4162] font-mono tracking-wide">
                    {activeWifi ? `CONNECTED TO: ${activeWifi}` : 'NOT CONNECTED'}
                  </span>
                </div>

                {/* Saved Networks List — TOP */}
                <div>
                  <h4 className="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Saved Networks</h4>
                  {savedNetworks.length === 0 ? (
                    <p className="text-xs text-gray-400 dark:text-slate-500 font-mono italic py-2">No saved Wi-Fi networks.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                      {savedNetworks.map((net, idx) => {
                        const isActive = net.is_active || activeWifi === net.ssid;
                        return (
                          <div key={idx} className={`flex items-center justify-between px-3 py-2 border ${isActive ? 'bg-green-50 border-green-200' : 'bg-gray-50 dark:bg-slate-900 border-gray-200 dark:border-slate-700'}`}>
                            <div className="flex items-center space-x-2 min-w-0">
                              <div className={`w-2 h-2 rounded-full shrink-0 ${isActive ? 'bg-green-500' : 'bg-gray-300'}`}></div>
                              <span className={`text-sm font-bold truncate ${isActive ? 'text-green-700' : 'text-gray-700 dark:text-slate-200'}`}>{net.ssid}</span>
                              {isActive && <span className="text-[10px] font-bold text-green-600 uppercase tracking-wider shrink-0">Active</span>}
                            </div>
                            <div className="flex items-center space-x-1.5 shrink-0 ml-2">
                              {!isActive && (
                                <button 
                                  onClick={() => handleConnectSaved(net.ssid)}
                                  disabled={wifiLoading}
                                  className="px-2.5 py-1 text-xs font-bold uppercase bg-primary dark:bg-blue-600 text-white hover:bg-opacity-90 transition-colors disabled:opacity-50"
                                >
                                  Connect
                                </button>
                              )}
                              <button 
                                onClick={() => handleForgetNetwork(net.ssid)}
                                disabled={wifiLoading}
                                className="p-1 text-gray-400 dark:text-slate-500 hover:text-red-600 transition-colors disabled:opacity-50"
                                title="Forget network"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Add New Network — BELOW */}
                <div className="pt-4 border-t border-gray-100 dark:border-slate-700">
                  <h4 className="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-3">Add New Network</h4>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-1">SSID (Network Name)</label>
                      <input 
                        type="text" 
                        value={ssid}
                        onChange={e => setSsid(e.target.value)}
                        placeholder="Enter network name"
                        className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-wider mb-1">Password</label>
                      <div className="relative">
                        <input 
                          type={showPassword ? "text" : "password"} 
                          value={password}
                          onChange={e => setPassword(e.target.value)}
                          placeholder="Enter password"
                          className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:text-slate-300 focus:outline-none transition-colors"
                        >
                          {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>
                    <button 
                      onClick={handleWifiConnect}
                      disabled={wifiLoading}
                      className="w-full bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity disabled:opacity-50"
                    >
                      {wifiLoading ? (
                        <><Loader2 size={16} className="animate-spin" /><span>Connecting...</span></>
                      ) : (
                        <><Wifi size={16} /><span>Connect & Save</span></>
                      )}
                    </button>
                  </div>
                </div>

                {/* Status Message */}
                {wifiStatus && (
                  <div className={`p-2 text-xs font-bold font-mono ${wifiStatus.isError ? 'text-red-600' : 'text-green-600'}`}>
                    {wifiStatus.msg}
                  </div>
                )}
              </div>
            </div>

            {/* Widget 2: Data Sharing (UDP Targets) */}
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-full min-h-0">
              <div className="flex justify-between items-center mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 shrink-0">
                <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider flex items-center">
                  <Activity size={16} className="mr-2" /> Data Sharing
                </h3>
                
                {/* Master Toggle */}
                <div className="flex items-center space-x-3">
                  <span className="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                    Data Forwarding
                  </span>
                  <button 
                    onClick={() => setDataForwarding(!dataForwarding)}
                    className={`w-12 h-6 rounded-full p-1 transition-colors flex items-center ${dataForwarding ? 'bg-[#10B981]' : 'bg-gray-300'}`}
                  >
                    <div className={`bg-white dark:bg-slate-800 w-4 h-4 rounded-full shadow-md transform transition-transform ${dataForwarding ? 'translate-x-6' : 'translate-x-0'}`} />
                  </button>
                </div>
              </div>

              <div className={`flex-1 flex flex-col min-h-0 transition-opacity ${!dataForwarding ? 'opacity-50 pointer-events-none' : ''}`}>
                <h4 className="text-xs font-bold text-gray-400 dark:text-slate-500 uppercase tracking-widest mb-3 shrink-0">Data Cast IPs</h4>
                
                {/* Saved Targets List */}
                <div className="flex-1 overflow-y-auto space-y-2 mb-4 pr-2">
                  {targets.length === 0 ? (
                      <p className="text-sm text-gray-400 dark:text-slate-500 font-mono italic">No targets configured.</p>
                  ) : (
                      targets.map((t, i) => (
                        <div key={i} className="flex flex-col border border-gray-200 dark:border-slate-700 p-3 bg-gray-50 dark:bg-slate-900">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-bold text-primary dark:text-blue-400 text-sm uppercase tracking-wider">{t.name}</span>
                            <button onClick={() => handleRemoveTarget(i)} className="text-gray-400 dark:text-slate-500 hover:text-red-600 transition-colors">
                              <X size={16} />
                            </button>
                          </div>
                          <div className="font-mono text-xs text-gray-600 dark:text-slate-300 flex items-center mb-2">
                            <span className="font-bold mr-2">IP:</span> {t.ip} 
                            <span className="mx-3 text-gray-300">|</span> 
                            <span className="font-bold mr-2">PORT:</span> {t.port}
                          </div>
                          {/* Per-target format toggle */}
                          <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-slate-700">
                            <span className="text-[10px] font-bold text-gray-400 dark:text-slate-500 uppercase tracking-wider">Data Format</span>
                            <div className="flex items-center bg-gray-200 dark:bg-slate-700 rounded-sm overflow-hidden">
                              <button
                                onClick={() => t.format !== 'corrected' && handleToggleFormat(i)}
                                className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                                  t.format === 'corrected' || !t.format
                                    ? 'bg-[#1a4162] text-white'
                                    : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:text-slate-200'
                                }`}
                              >
                                m/s²
                              </button>
                              <button
                                onClick={() => t.format !== 'raw' && handleToggleFormat(i)}
                                className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                                  t.format === 'raw'
                                    ? 'bg-amber-600 text-white'
                                    : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:text-slate-200'
                                }`}
                              >
                                Raw Counts
                              </button>
                            </div>
                          </div>
                          {t.format === 'raw' && (
                            <p className="text-[10px] text-amber-700 font-mono mt-1.5 leading-relaxed">
                              ⚠ Server needs the StationXML response file to convert counts → m/s²
                            </p>
                          )}
                        </div>
                      ))
                  )}
                </div>

                {/* Add Target Form */}
                <div className="shrink-0 space-y-4 pt-4 border-t border-gray-100 dark:border-slate-700">
                  <div className="flex space-x-2 items-end bg-gray-50 dark:bg-slate-900 p-3 border border-gray-200 dark:border-slate-700">
                    <div className="flex-1">
                      <label className="block text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-1">Name</label>
                      <input type="text" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Main Server" className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs" />
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-1">IP Address</label>
                      <input type="text" value={newIp} onChange={e => setNewIp(e.target.value)} placeholder="192.168.1.50" className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs" />
                    </div>
                    <div className="w-20">
                      <label className="block text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-1">Port</label>
                      <input type="number" value={newPort} onChange={e => setNewPort(e.target.value)} className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs" />
                    </div>
                    <button onClick={handleAddTarget} className="bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-300 px-3 py-1.5 flex items-center font-bold text-xs uppercase transition-colors h-[30px]">
                      <Plus size={14} />
                    </button>
                  </div>
                  {/* Format selector for new target */}
                  <div className="flex items-center justify-between bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 px-3 py-2">
                    <span className="text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider">New Target Format</span>
                    <div className="flex items-center bg-gray-200 dark:bg-slate-700 rounded-sm overflow-hidden">
                      <button
                        onClick={() => setNewFormat('corrected')}
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                          newFormat === 'corrected' ? 'bg-[#1a4162] text-white' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:text-slate-200'
                        }`}
                      >
                        Corrected m/s²
                      </button>
                      <button
                        onClick={() => setNewFormat('raw')}
                        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider transition-colors ${
                          newFormat === 'raw' ? 'bg-amber-600 text-white' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:text-slate-200'
                        }`}
                      >
                        Raw Counts
                      </button>
                    </div>
                  </div>
                  
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                  >
                    <Save size={16} />
                    <span>Save Targets</span>
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Tab 3: System */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'system' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-2 gap-6 h-full">
            {/* Calibration Settings */}
            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                <SettingsIcon size={16} className="mr-2" /> Calibration Settings
              </h3>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Calibration Time (seconds)</label>
                  <input 
                    type="number" 
                    value={calibrationTime}
                    onChange={e => setCalibrationTime(e.target.value)}
                    className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                  <p className="text-xs text-gray-400 dark:text-slate-500 mt-2 font-mono">Recommended: 60 seconds</p>
                </div>

                <div>
                  <label className="block text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Data Retention (days)</label>
                  <input 
                    type="number" 
                    value={retentionDays}
                    onChange={e => setRetentionDays(e.target.value)}
                    className="w-full border border-gray-300 dark:border-slate-600 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                  <p className="text-xs text-gray-400 dark:text-slate-500 mt-2 font-mono">Older miniSEED files will be deleted.</p>
                </div>

                <div className="pt-2 border-t border-gray-100 dark:border-slate-700">
                  <span className="block text-xs font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-1">Archive Size</span>
                  <span className="text-sm font-mono font-bold text-[#1a4162] bg-gray-100 dark:bg-slate-800 px-3 py-1 inline-block">
                    {(archiveSize / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>

                <div className="flex justify-end pt-4 border-t border-gray-100 dark:border-slate-700">
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                  >
                    <Save size={16} />
                    <span>Save Calibration</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Right Column: UI Settings & System Actions */}
            <div className="space-y-6">
              {/* UI Settings */}
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-fit">
                <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                  <Palette size={16} className="mr-2" /> UI Settings
                </h3>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3 text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                    {theme === 'dark' ? <Moon size={20} /> : <Sun size={20} />}
                    <span>{theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</span>
                  </div>
                  <button 
                    onClick={toggleTheme}
                    className={`w-14 h-7 rounded-full p-1 transition-colors flex items-center ${theme === 'dark' ? 'bg-[#10B981]' : 'bg-gray-300 dark:bg-slate-600'}`}
                  >
                    <div className={`bg-white w-5 h-5 rounded-full shadow-md transform transition-transform ${theme === 'dark' ? 'translate-x-7' : 'translate-x-0'}`} />
                  </button>
                </div>
              </div>

              {/* System Actions */}
              <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-6 shadow-sm flex flex-col h-fit">
                <h3 className="text-sm font-bold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 dark:border-slate-700 flex items-center shrink-0">
                  <Power size={16} className="mr-2" /> System Actions
                </h3>
                <div className="space-y-6">
                  <button 
                    onClick={() => setIsRestartModalOpen(true)}
                    className="w-full bg-red-600 text-white font-bold tracking-widest uppercase px-6 py-4 flex items-center justify-center space-x-2 hover:bg-red-700 transition-colors"
                  >
                    <Power size={20} />
                    <span>Restart Sensor</span>
                  </button>
                  <p className="text-sm text-gray-500 dark:text-slate-400 font-mono text-center">Reboots the Raspberry Pi system. Telemetry will be temporarily unavailable.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Restart Confirmation Modal */}
      {isRestartModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 p-6 max-w-md w-full shadow-lg border border-gray-200 dark:border-slate-700">
            <h3 className="text-lg font-bold text-red-600 mb-2 uppercase tracking-wide flex items-center">
              <Power size={20} className="mr-2" /> Confirm Restart
            </h3>
            <p className="text-sm text-gray-600 dark:text-slate-300 mb-6 font-mono leading-relaxed">
              Are you sure you want to restart the sensor? Telemetry will be interrupted while the system reboots.
            </p>
            <div className="flex space-x-4">
              <button 
                onClick={() => setIsRestartModalOpen(false)}
                className="flex-1 bg-gray-100 dark:bg-slate-800 hover:bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-slate-200 font-bold uppercase tracking-wider py-2 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={handleRestartConfirm}
                className="flex-1 bg-red-600 hover:bg-red-700 text-white font-bold uppercase tracking-wider py-2 transition-colors"
              >
                Confirm Restart
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Network Switch Modal — NON-DISMISSIBLE */}
      {switchModal && (
        <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 p-8 max-w-lg w-full shadow-2xl border border-gray-200 dark:border-slate-700">
            <div className="flex items-center justify-center mb-6">
              <div className="w-16 h-16 rounded-full bg-blue-50 border-2 border-blue-200 flex items-center justify-center">
                <Loader2 size={32} className="animate-spin text-primary dark:text-blue-400" />
              </div>
            </div>
            <h3 className="text-lg font-bold text-[#1a4162] mb-3 uppercase tracking-wide text-center">
              Switching Network
            </h3>
            <p className="text-sm text-gray-600 dark:text-slate-300 mb-4 font-mono leading-relaxed text-center">
              Sensor is connecting to <strong className="text-[#1a4162]">{switchModal.ssid}</strong>.
              Your connection to this dashboard will now be lost.
            </p>
            <div className="bg-amber-50 border border-amber-200 p-4 mb-4">
              <p className="text-xs font-bold text-amber-800 font-mono leading-relaxed text-center">
                Please connect this computer to <strong>"{switchModal.ssid}"</strong> and 
                navigate to the sensor's new local IP address to regain access.
              </p>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-slate-500 font-mono text-center uppercase tracking-wider">
              This modal will remain until the page is refreshed on the new network.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

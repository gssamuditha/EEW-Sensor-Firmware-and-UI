import { useState, useEffect } from 'react';
import { Save, Plus, X, Wifi, Power, MapPin, Target, Monitor, Settings as SettingsIcon } from 'lucide-react';
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
  const [targets, setTargets] = useState([{ ip: '127.0.0.1', port: 2098 }]);
  const [newIp, setNewIp] = useState('');
  const [newPort, setNewPort] = useState(2098);
  const [lat, setLat] = useState(0.0);
  const [lon, setLon] = useState(0.0);
  const [deviceName, setDeviceName] = useState('CRISIS-NODE-01');
  const [calibrationTime, setCalibrationTime] = useState(60);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  
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
        if (data.calibration_time) setCalibrationTime(data.calibration_time);
        if (data.wifi_ssid) setSsid(data.wifi_ssid);
        if (data.wifi_password) setPassword(data.wifi_password);
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
    if (!newIp) return;
    setTargets([...targets, { ip: newIp, port: parseInt(newPort) }]);
    setNewIp('');
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
          calibration_time: parseInt(calibrationTime)
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
    showWifiStatus('Connecting to Wi-Fi...');
    try {
      const res = await fetch('/api/wifi/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        showWifiStatus('Wi-Fi Connected successfully.');
      } else {
        showWifiStatus('Failed to connect: ' + data.message, true);
      }
    } catch (e) {
      console.error(e);
      showWifiStatus('Network error during Wi-Fi connect.', true);
    }
  };

  const handleWifiForget = async () => {
    try {
      const res = await fetch('/api/wifi/forget', { method: 'POST' });
      if (res.ok) {
        setSsid('');
        setPassword('');
        showWifiStatus('Wi-Fi Network Forgotten.');
      }
    } catch (e) {
      console.error(e);
      showWifiStatus('Failed to forget Wi-Fi.', true);
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
    <div className="p-6 h-full bg-gray-50 flex flex-col w-full overflow-hidden">
      
      <div className="w-full flex justify-between items-center mb-4 shrink-0">
        <h2 className="text-2xl font-bold text-primary tracking-wide uppercase">System Configuration</h2>
        {status && (
          <div className={`px-4 py-2 text-sm font-bold font-mono shadow-sm ${status.isError ? 'bg-red-50 text-red-600 border border-red-200' : 'bg-green-50 text-green-600 border border-green-200'}`}>
            {status.msg}
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="w-full border-b border-gray-200 mb-6 shrink-0">
        <ul className="flex flex-wrap -mb-px text-sm font-bold text-center">
          {tabs.map(tab => (
            <li className="mr-8" key={tab.id}>
              <button
                onClick={() => setActiveTab(tab.id)}
                className={`inline-block py-3 border-b-2 transition-all duration-200 ${
                  activeTab === tab.id 
                    ? 'text-[#1a4162] border-[#1a4162]' 
                    : 'text-gray-400 border-transparent hover:text-gray-600 hover:border-gray-300'
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
            
            {/* Widget 1: Device Details */}
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
                <Monitor size={16} className="mr-2" /> Device Details
              </h3>
              <div className="flex-1 flex flex-col space-y-4">
                <div>
                  <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Device Name</label>
                  <input 
                    type="text" 
                    value={deviceName}
                    onChange={e => setDeviceName(e.target.value)}
                    placeholder="CRISIS-NODE-01"
                    className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>

                <div className="flex justify-end pt-4 border-t border-gray-100">
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                  >
                    <Save size={16} />
                    <span>Save Name</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Widget 2: Device Location */}
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-full min-h-0">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
                <MapPin size={16} className="mr-2" /> Device Location
              </h3>
              <div className="flex-1 flex flex-col min-h-0">
                <div className="flex-1 min-h-0 mb-4 border border-gray-200 z-0 relative">
                  <MapContainer center={[lat || 0, lon || 0]} zoom={2} scrollWheelZoom={true} style={{ height: '100%', width: '100%' }}>
                    <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                    <LocationMarker position={{lat, lng: lon}} setPosition={(pos) => { setLat(pos.lat); setLon(pos.lng); }} />
                  </MapContainer>
                </div>
                <div className="grid grid-cols-2 gap-4 shrink-0 mb-4">
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Latitude</label>
                    <input 
                      type="number" step="any"
                      value={lat}
                      onChange={e => setLat(parseFloat(e.target.value) || 0)}
                      className="w-full border border-gray-300 rounded-none px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Longitude</label>
                    <input 
                      type="number" step="any"
                      value={lon}
                      onChange={e => setLon(parseFloat(e.target.value) || 0)}
                      className="w-full border border-gray-300 rounded-none px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-4 border-t border-gray-100 shrink-0">
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
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
            
            {/* Widget 1: Wi-Fi Settings */}
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
                <Wifi size={16} className="mr-2" /> Wi-Fi Configuration
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">SSID (Network Name)</label>
                  <input 
                    type="text" 
                    value={ssid}
                    onChange={e => setSsid(e.target.value)}
                    className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Wi-Fi Password</label>
                  <input 
                    type="password" 
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>
                {wifiStatus && (
                  <div className={`p-2 text-xs font-bold font-mono ${wifiStatus.isError ? 'text-red-600' : 'text-green-600'}`}>
                    {wifiStatus.msg}
                  </div>
                )}
                <div className="flex space-x-4 pt-4 border-t border-gray-100">
                  <button 
                    onClick={handleWifiConnect}
                    className="flex-1 bg-primary text-white font-bold tracking-widest uppercase py-2 flex items-center justify-center hover:bg-opacity-90 transition-opacity"
                  >
                    Connect / Save
                  </button>
                  <button 
                    onClick={handleWifiForget}
                    className="flex-1 bg-red-50 text-red-600 border border-red-200 font-bold tracking-widest uppercase py-2 flex items-center justify-center hover:bg-red-100 transition-colors"
                  >
                    Forget Network
                  </button>
                </div>
              </div>
            </div>

            {/* Widget 2: UDP Targets */}
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-full min-h-0">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
                <Target size={16} className="mr-2" /> UDP Target Servers
              </h3>
              <div className="flex-1 flex flex-col min-h-0">
                <div className="flex-1 overflow-y-auto space-y-2 mb-4 pr-2">
                  {targets.length === 0 ? (
                      <p className="text-sm text-gray-400 font-mono italic">No targets configured.</p>
                  ) : (
                      targets.map((t, i) => (
                        <div key={i} className="flex items-center justify-between border border-gray-200 p-2 bg-gray-50">
                          <div className="font-mono text-sm">
                            <span className="font-bold text-gray-600">IP:</span> {t.ip} <span className="mx-2 text-gray-300">|</span> <span className="font-bold text-gray-600">PORT:</span> {t.port}
                          </div>
                          <button onClick={() => handleRemoveTarget(i)} className="text-gray-400 hover:text-red-600 transition-colors">
                            <X size={18} />
                          </button>
                        </div>
                      ))
                  )}
                </div>
                <div className="shrink-0 space-y-4 pt-4 border-t border-gray-100">
                  <div className="flex space-x-2 items-end bg-gray-50 p-3 border border-gray-200">
                    <div className="flex-1">
                      <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">IP Address</label>
                      <input type="text" value={newIp} onChange={e => setNewIp(e.target.value)} placeholder="192.168.1.100" className="w-full border border-gray-300 rounded-none px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-sm" />
                    </div>
                    <div className="w-24">
                      <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Port</label>
                      <input type="number" value={newPort} onChange={e => setNewPort(e.target.value)} className="w-full border border-gray-300 rounded-none px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-sm" />
                    </div>
                    <button onClick={handleAddTarget} className="bg-gray-200 text-gray-700 hover:bg-gray-300 px-3 py-1.5 flex items-center font-bold text-xs uppercase transition-colors h-[34px]">
                      <Plus size={14} className="mr-1" /> Add
                    </button>
                  </div>
                  
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
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
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
                <SettingsIcon size={16} className="mr-2" /> Calibration Settings
              </h3>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Calibration Time (seconds)</label>
                  <input 
                    type="number" 
                    value={calibrationTime}
                    onChange={e => setCalibrationTime(e.target.value)}
                    className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                  <p className="text-xs text-gray-400 mt-2 font-mono">Recommended: 60 seconds</p>
                </div>

                <div className="flex justify-end pt-4 border-t border-gray-100">
                  <button 
                    onClick={handleSaveSettings}
                    className="bg-primary text-white font-bold tracking-widest uppercase px-6 py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity w-full"
                  >
                    <Save size={16} />
                    <span>Save Calibration</span>
                  </button>
                </div>
              </div>
            </div>

            {/* System Actions */}
            <div className="bg-white border border-gray-200 p-6 shadow-sm flex flex-col h-fit">
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 pb-2 border-b border-gray-100 flex items-center shrink-0">
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
                <p className="text-sm text-gray-500 font-mono text-center">Reboots the Raspberry Pi system. Telemetry will be temporarily unavailable.</p>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Restart Confirmation Modal */}
      {isRestartModalOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white p-6 max-w-md w-full shadow-lg border border-gray-200">
            <h3 className="text-lg font-bold text-red-600 mb-2 uppercase tracking-wide flex items-center">
              <Power size={20} className="mr-2" /> Confirm Restart
            </h3>
            <p className="text-sm text-gray-600 mb-6 font-mono leading-relaxed">
              Are you sure you want to restart the sensor? Telemetry will be interrupted while the system reboots.
            </p>
            <div className="flex space-x-4">
              <button 
                onClick={() => setIsRestartModalOpen(false)}
                className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-bold uppercase tracking-wider py-2 transition-colors"
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
    </div>
  );
}

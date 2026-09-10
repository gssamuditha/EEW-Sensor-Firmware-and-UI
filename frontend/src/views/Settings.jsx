import { useState, useEffect } from 'react';
import { ArrowDownOnSquareIcon as Save, PlusIcon as Plus, XMarkIcon as X, WifiIcon as Wifi, PowerIcon as Power, MapPinIcon as MapPin, ComputerDesktopIcon as Monitor, Cog6ToothIcon as SettingsIcon, ChartBarIcon as Activity, EyeIcon as Eye, EyeSlashIcon as EyeOff, ArrowPathIcon as Loader2, TrashIcon as Trash2, SunIcon as Sun, MoonIcon as Moon, PaintBrushIcon as Palette, CircleStackIcon as Database, LockClosedIcon as Lock } from '@heroicons/react/24/solid';
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
import AuthModal from '../components/AuthModal';
import { useAuth } from '../components/useAuth';

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

  // ── Auth ────────────────────────────────────────────────────────────────────
  const { requireAuth, showAuthModal, handleAuthSuccess, handleAuthCancel } = useAuth();

  // ── Change-password form state ───────────────────────────────────────────────
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordStatus, setPasswordStatus] = useState(null);
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  // ── Recovery form state ──────────────────────────────────────────────────────
  const [recoveryAuthPw, setRecoveryAuthPw] = useState('');
  const [recoveryQ1, setRecoveryQ1] = useState('What city were you born in?');
  const [recoveryA1, setRecoveryA1] = useState('');
  const [recoveryQ2, setRecoveryQ2] = useState('What was the name of your first pet?');
  const [recoveryA2, setRecoveryA2] = useState('');
  const [recoveryStatus, setRecoveryStatus] = useState(null);
  const [isRecoveryConfigured, setIsRecoveryConfigured] = useState(false);

  const [targets, setTargets] = useState([{ name: 'Main Server', ip: '127.0.0.1', port: 2098, format: 'corrected' }]);
  const [hasUnsavedTargets, setHasUnsavedTargets] = useState(false);
  const [targetError, setTargetError] = useState('');
  const [newName, setNewName] = useState('');
  const [newIp, setNewIp] = useState('');
  const [newPort, setNewPort] = useState(2098);
  const [newFormat, setNewFormat] = useState('corrected');
  const [lat, setLat] = useState(0.0);
  const [lon, setLon] = useState(0.0);
  const [deviceName, setDeviceName] = useState('CRISIS-NODE-01');
  const [deviceId, setDeviceId] = useState('T0021');
  const [ownerName, setOwnerName] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');
  const [calibrationTime, setCalibrationTime] = useState(60);
  const [retentionDays, setRetentionDays] = useState(7);
  const [archiveSize, setArchiveSize] = useState(0);
  const [elevation, setElevation] = useState(0.0);
  const [floorUnit, setFloorUnit] = useState(0);
  const [totalFloors, setTotalFloors] = useState(1);
  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [dataForwarding, setDataForwarding] = useState(true);
  const [wifiEnabled, setWifiEnabled] = useState(true);
  const [activeWifi, setActiveWifi] = useState(null);
  const [savedNetworks, setSavedNetworks] = useState([]);
  const [wifiLoading, setWifiLoading] = useState(false);
  const [switchModal, setSwitchModal] = useState(null); // null or { ssid: string }

  const [status, setStatus] = useState(null);
  const [wifiStatus, setWifiStatus] = useState(null);
  const [activeTab, setActiveTab] = useState('general');

  // --- System Action Modal State ---
  const [confirmModal, setConfirmModal] = useState(null); // null | 'restart' | 'shutdown'

  const openConfirmModal = (action) => {
    setConfirmModal(action);
  };

  const closeConfirmModal = () => {
    setConfirmModal(null);
  };

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.targets && data.targets.length > 0) setTargets(data.targets);
        setLat(data.latitude || 0.0);
        setLon(data.longitude || 0.0);
        if (data.device_name) setDeviceName(data.device_name);
        if (data.device_id) setDeviceId(data.device_id);
        if (data.owner_name !== undefined) setOwnerName(data.owner_name);
        if (data.owner_email !== undefined) setOwnerEmail(data.owner_email);
        if (data.elevation !== undefined) setElevation(data.elevation);
        if (data.floor_unit !== undefined) setFloorUnit(data.floor_unit);
        if (data.total_floors !== undefined) setTotalFloors(data.total_floors);
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
        if (data.wifi_enabled !== undefined) setWifiEnabled(data.wifi_enabled);
      })
      .catch(console.error);

    fetch('/api/auth/recovery/questions')
      .then(res => {
        if (res.ok) setIsRecoveryConfigured(true);
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
    if (!newIp || !newName) {
      setTargetError('Name and IP are required.');
      return;
    }
    const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipv4Regex.test(newIp) || newIp.split('.').some(p => parseInt(p) > 255)) {
      setTargetError('Invalid IPv4 address format.');
      return;
    }
    const port = parseInt(newPort);
    if (isNaN(port) || port < 1 || port > 65535) {
      setTargetError('Port must be between 1 and 65535.');
      return;
    }

    setTargetError('');
    setTargets([...targets, { name: newName, ip: newIp, port, format: newFormat }]);
    setNewName('');
    setNewIp('');
    setNewFormat('corrected');
    setHasUnsavedTargets(true);
  };

  const handleToggleFormat = (index) => {
    setTargets(targets.map((t, i) =>
      i === index ? { ...t, format: t.format === 'corrected' ? 'raw' : 'corrected' } : t
    ));
    setHasUnsavedTargets(true);
  };

  const handleRemoveTarget = (index) => {
    setTargets(targets.filter((_, i) => i !== index));
    setHasUnsavedTargets(true);
  };

  // Protected: opens auth modal then fires the fetch once token is available
  const handleSaveSettings = () => {
    requireAuth(async (authToken) => {
      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Auth-Token': authToken,
          },
          body: JSON.stringify({
            targets,
            latitude: parseFloat(lat),
            longitude: parseFloat(lon),
            elevation: parseFloat(elevation),
            floor_unit: parseInt(floorUnit),
            total_floors: parseInt(totalFloors),
            device_name: deviceName,
            device_id: deviceId,
            owner_name: ownerName,
            owner_email: ownerEmail,
            calibration_time: parseInt(calibrationTime),
            retention_days: parseInt(retentionDays),
            data_forwarding: dataForwarding
          })
        });
        if (res.ok) {
          showStatus('Configuration saved successfully.');
          setHasUnsavedTargets(false);
        } else {
          showStatus('Error saving configuration.', true);
        }
      } catch (e) {
        console.error(e);
        showStatus('Error saving configuration.', true);
      }
    });
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
        // Backend accepted it will switch networks in ~3 seconds
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

  // Protected: auth modal → confirmation (for disable) → API call
  const handleWifiToggle = (enabled) => {
    requireAuth(async (authToken) => {
      if (!enabled) {
        const confirmed = window.confirm(
          'Warning: Disabling Wi-Fi will disconnect you immediately if you are currently accessing the dashboard over Wi-Fi. Continue?'
        );
        if (!confirmed) return;
      }

      setWifiEnabled(enabled);
      if (!enabled) setWifiStatus('');

      try {
        const res = await fetch('/api/wifi/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Auth-Token': authToken },
          body: JSON.stringify({ enabled })
        });
        const data = await res.json();
        if (data.status !== 'ok') {
          setWifiEnabled(!enabled);
          showWifiStatus('Failed to toggle Wi-Fi: ' + data.message, true);
        }
      } catch (e) {
        console.error(e);
        setWifiEnabled(!enabled);
        showWifiStatus('Error toggling Wi-Fi', true);
      }
    });
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

  // Protected: confirm modal closes first, then auth modal, then API call
  const handleSystemActionConfirm = () => {
    const action = confirmModal; // capture before closing
    setConfirmModal(null);
    requireAuth(async (authToken) => {
      const endpoint = action === 'shutdown' ? '/api/system/shutdown' : '/api/system/restart';
      const successMsg = action === 'shutdown' ? 'Shutting down Pi…' : 'System is restarting…';
      try {
        await fetch(endpoint, {
          method: 'POST',
          headers: { 'X-Auth-Token': authToken },
        });
        showStatus(successMsg);
      } catch (e) {
        console.error(e);
        showStatus('Failed to trigger action.', true);
      }
    });
  };

  // Change-password form handler (uses its own credential verification, no session token needed)
  const handleChangePassword = async () => {
    if (!newPassword) {
      setPasswordStatus({ msg: 'New password is required.', isError: true }); return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ msg: 'Passwords do not match.', isError: true }); return;
    }
    if (newPassword.length < 4) {
      setPasswordStatus({ msg: 'Password must be at least 4 characters.', isError: true }); return;
    }
    try {
      const res = await fetch('/api/auth/set_password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: currentPassword || undefined,
          new_password: newPassword,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setPasswordStatus({ msg: 'Password updated successfully.', isError: false });
        setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
        setTimeout(() => setPasswordStatus(null), 4000);
      } else {
        setPasswordStatus({ msg: data.detail || 'Failed to update password.', isError: true });
      }
    } catch {
      setPasswordStatus({ msg: 'Network error.', isError: true });
    }
  };

  const handleRecoverySetup = async () => {
    if (!recoveryAuthPw) {
      setRecoveryStatus({ msg: 'Admin password required.', isError: true }); return;
    }
    if (!recoveryQ1 || !recoveryA1 || !recoveryQ2 || !recoveryA2) {
      setRecoveryStatus({ msg: 'Please provide both questions and answers.', isError: true }); return;
    }
    try {
      const res = await fetch('/api/auth/recovery/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: recoveryAuthPw,
          q1: recoveryQ1,
          a1: recoveryA1,
          q2: recoveryQ2,
          a2: recoveryA2
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setRecoveryStatus({ msg: 'Recovery questions saved successfully.', isError: false });
        setIsRecoveryConfigured(true);
        setRecoveryAuthPw(''); setRecoveryA1(''); setRecoveryA2('');
        setTimeout(() => setRecoveryStatus(null), 4000);
      } else {
        setRecoveryStatus({ msg: data.detail || 'Failed to set recovery questions.', isError: true });
      }
    } catch {
      setRecoveryStatus({ msg: 'Network error.', isError: true });
    }
  };


  const tabs = [
    { id: 'general', label: 'General' },
    { id: 'network', label: 'Network' },
    { id: 'system', label: 'System' },
    { id: 'security', label: 'Security' }
  ];

  return (
    <div className="p-3 md:p-6 h-full bg-slate-50 dark:bg-slate-900 flex flex-col w-full overflow-hidden">

      <div className="w-full flex flex-col md:flex-row justify-between items-start md:items-center gap-2 md:gap-0 mb-4 shrink-0">
        <h2 className="text-2xl font-bold text-primary dark:text-sky-400 tracking-wide">System Configuration</h2>
        {status && (
          <div className={`px-4 py-2 text-sm font-bold font-mono shadow-sm ${status.isError ? 'bg-red-50 text-red-600 border border-red-200' : 'bg-green-50 text-emerald-600 dark:text-emerald-500 border border-green-200'}`}>
            {status.msg}
          </div>
        )}
      </div>

      {/* Tabs Navigation */}
      <div className="w-full border-b border-slate-100 dark:border-slate-700 mb-6 shrink-0">
        <ul className="flex flex-wrap -mb-px text-sm font-bold text-center">
          {tabs.map(tab => (
            <li className="mr-8" key={tab.id}>
              <button
                onClick={() => setActiveTab(tab.id)}
                className={`inline-block py-3 border-b-2 transition-all duration-200 ${activeTab === tab.id
                  ? 'text-[#1a4162] dark:text-sky-400 border-[#1a4162] dark:border-sky-400'
                  : 'text-slate-400 dark:text-slate-400 border-transparent hover:text-slate-600 dark:text-slate-200 hover:border-slate-200 dark:border-slate-600'
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

        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'general' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full overflow-y-auto p-1 pb-6 w-full">

            {/* Widget 1: Station & Operator Details */}
            <div className="lg:col-span-1 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-full">
              <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 shrink-0">
                Station Details
              </h3>
              <div className="flex-1 flex flex-col space-y-4">
                
                {/* Column 1: Device Name */}
                <div>
                  <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Device Name</label>
                  <input
                    type="text"
                    value={deviceName}
                    onChange={e => setDeviceName(e.target.value)}
                    placeholder="CRISIS-NODE-01"
                    className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>

                {/* Column 2: Owner's Details */}
                <div>
                  <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Device Owner's Name</label>
                  <input
                    type="text"
                    value={ownerName}
                    onChange={e => setOwnerName(e.target.value)}
                    placeholder="First Last"
                    className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>

                {/* Column 3: Email */}
                <div>
                  <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Email</label>
                  <input
                    type="email"
                    value={ownerEmail}
                    onChange={e => setOwnerEmail(e.target.value)}
                    placeholder="operator@example.com"
                    className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                  />
                </div>

                <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700/50 shrink-0">
                  <button
                    onClick={handleSaveSettings}
                    className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest px-6 py-2 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
                  >
                    <Save className="w-4 h-4" />
                    <span>Save Details</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Widget 2: Device Location */}
            <div className="lg:col-span-2 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-full">
              <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0">
                Device Location
              </h3>
              
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
                {/* Left Column: Map */}
                <div className="lg:col-span-2 h-[300px] lg:h-full border border-slate-100 dark:border-slate-700 z-0 relative rounded-md overflow-hidden">
                  <MapContainer center={[lat || 0, lon || 0]} zoom={2} scrollWheelZoom={true} style={{ height: '100%', width: '100%' }}>
                    <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                    <LocationMarker position={{ lat, lng: lon }} setPosition={(pos) => { setLat(pos.lat); setLon(pos.lng); }} />
                  </MapContainer>
                </div>

                {/* Right Column: Inputs */}
                <div className="flex flex-col h-full space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Latitude</label>
                    <input
                      type="number" step="any"
                      value={lat}
                      onChange={e => setLat(parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Longitude</label>
                    <input
                      type="number" step="any"
                      value={lon}
                      onChange={e => setLon(parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Elevation (m)</label>
                    <input
                      type="number" step="any"
                      value={elevation}
                      onChange={e => setElevation(parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Floor Unit</label>
                      <input
                        type="number"
                        value={floorUnit}
                        onChange={e => setFloorUnit(parseInt(e.target.value) || 0)}
                        className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Total Floors</label>
                      <input
                        type="number" min="1"
                        value={totalFloors}
                        onChange={e => setTotalFloors(parseInt(e.target.value) || 1)}
                        className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm"
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-1 px-1">
                    <p className="text-[10px] text-slate-400 dark:text-slate-400 font-mono w-full">(Ground floor = 0, Basement = -1, First floor = 1)</p>
                    <p className="text-[10px] text-slate-400 dark:text-emerald-500 font-bold tracking-wide w-full">* The sensor's exact location will not be revealed to the public.</p>
                  </div>

                  <div className="flex justify-end pt-4 border-t border-slate-100 dark:border-slate-700/50 mt-auto shrink-0">
                    <button
                      onClick={handleSaveSettings}
                      className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest px-6 py-2 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
                    >
                      <Save className="w-4 h-4" />
                      <span>Save Location</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Tab 2: Network */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'network' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 h-full overflow-y-auto p-1 pb-6">

            {/* Widget 1: Wi-Fi Manager */}
            <div className="lg:col-span-2 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-full">
              <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 shrink-0">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider">
                  Wi-Fi Configuration
                </h3>
                <button
                  onClick={() => handleWifiToggle(!wifiEnabled)}
                  className={`w-12 h-6 rounded-full p-1 transition-colors flex items-center ${wifiEnabled ? 'bg-[#10B981]' : 'bg-gray-300'}`}
                >
                  <div className={`bg-white dark:bg-slate-800 w-4 h-4 rounded-full shadow-md transform transition-transform ${wifiEnabled ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>

              {!wifiEnabled && (
                <div className="flex flex-col items-center justify-center py-8 text-center bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-dashed border-slate-200 dark:border-slate-700">
                  <p className="text-sm font-medium text-slate-500 dark:text-slate-400">Wi-Fi is currently disabled.</p>
                </div>
              )}
              {wifiEnabled && (
                <div className="space-y-4 flex-1 flex flex-col min-h-0">

                  {/* Active Connection Indicator */}
                  <div className="flex items-center space-x-2 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg shadow-sm px-4 py-2">
                    <div className={`w-2 h-2 rounded-full ${activeWifi ? 'bg-emerald-500' : 'bg-gray-400'}`}></div>
                    <span className="text-xs font-bold text-[#1a4162] dark:text-sky-300 font-mono tracking-wide">
                      {activeWifi ? `CONNECTED TO: ${activeWifi}` : 'NOT CONNECTED'}
                    </span>
                  </div>

                  {/* Saved Networks List — TOP */}
                  <div>
                    <h4 className="text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-2">Saved Networks</h4>
                    {savedNetworks.length === 0 ? (
                      <p className="text-xs text-slate-400 dark:text-slate-400 font-mono italic py-2">No saved Wi-Fi networks.</p>
                    ) : (
                      <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                        {savedNetworks.map((net, idx) => {
                          const isActive = net.is_active || activeWifi === net.ssid;
                          return (
                            <div key={idx} className={`flex items-center justify-between px-3 py-2 border ${isActive ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/30 dark:border-emerald-800' : 'bg-slate-50 dark:bg-slate-900 border-slate-100 dark:border-slate-700'}`}>
                              <div className="flex items-center space-x-2 min-w-0">
                                <div className={`w-2 h-2 rounded-full shrink-0 ${isActive ? 'bg-emerald-500' : 'bg-gray-300'}`}></div>
                                <span className={`text-sm font-bold truncate ${isActive ? 'text-emerald-700 dark:text-emerald-400' : 'text-gray-700 dark:text-slate-200'}`}>{net.ssid}</span>
                                {isActive && <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-500 uppercase tracking-wider shrink-0">Active</span>}
                              </div>
                              <div className="flex items-center space-x-1.5 shrink-0 ml-2">
                                {!isActive && (
                                  <button
                                    onClick={() => handleConnectSaved(net.ssid)}
                                    disabled={wifiLoading}
                                    className="px-2.5 py-1 text-xs font-bold uppercase bg-primary dark:bg-sky-600 text-white rounded-md hover:bg-opacity-90 transition-all shadow-sm disabled:opacity-50"
                                  >
                                    Connect
                                  </button>
                                )}
                                <button
                                  onClick={() => handleForgetNetwork(net.ssid)}
                                  disabled={wifiLoading}
                                  className="p-1 text-slate-400 dark:text-slate-400 hover:text-red-600 transition-colors disabled:opacity-50"
                                  title="Forget network"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Add New Network — BELOW */}
                  <div className="pt-4 border-t border-slate-100 dark:border-slate-700/50 mt-auto shrink-0">
                    <h4 className="text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-3">Add New Network</h4>
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 uppercase tracking-wider mb-1">SSID</label>
                        <input
                          type="text"
                          value={ssid}
                          onChange={e => setSsid(e.target.value)}
                          placeholder="Enter network name"
                          className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Password</label>
                        <div className="relative">
                          <input
                            type={showPassword ? "text" : "password"}
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            placeholder="Enter password"
                            className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm pr-10"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 dark:text-slate-400 hover:text-slate-600 dark:text-slate-200 focus:outline-none transition-colors"
                          >
                            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                      <button
                        onClick={handleWifiConnect}
                        disabled={wifiLoading}
                        className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest py-2 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity disabled:opacity-50"
                      >
                        {wifiLoading ? (
                          <><Loader2 className="w-4 h-4 animate-spin" /><span>Connecting...</span></>
                        ) : (
                          <><Wifi className="w-4 h-4" /><span>Connect & Save</span></>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Status Message */}
                  {wifiStatus && (
                    <div className={`p-2 text-xs font-bold font-mono ${wifiStatus.isError ? 'text-red-600' : 'text-emerald-600 dark:text-emerald-500'}`}>
                      {wifiStatus.msg}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Widget 2: Data Sharing (UDP Targets) */}
            <div className="lg:col-span-3 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col">
              <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 shrink-0">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider">
                  Data Sharing
                </h3>

                {/* Master Toggle */}
                <div className="flex items-center space-x-3">
                  <span className="text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider">
                    Data Forwarding
                  </span>
                  <button
                    onClick={() => requireAuth(() => setDataForwarding(!dataForwarding))}
                    className={`w-12 h-6 rounded-full p-1 transition-colors flex items-center ${dataForwarding ? 'bg-[#10B981]' : 'bg-gray-300'}`}
                  >
                    <div className={`bg-white dark:bg-slate-800 w-4 h-4 rounded-full shadow-md transform transition-transform ${dataForwarding ? 'translate-x-6' : 'translate-x-0'}`} />
                  </button>
                </div>
              </div>

              <div className={`flex-1 flex flex-col min-h-0 transition-opacity ${!dataForwarding ? 'opacity-50 pointer-events-none' : ''}`}>
                <h4 className="text-xs font-bold text-slate-400 dark:text-slate-400 tracking-widest mb-3 shrink-0">Data Forwarding IPs</h4>

                {/* Saved Targets List */}
                <div className="flex-1 overflow-y-auto space-y-2 mb-4 pr-2">
                  {targets.length === 0 ? (
                    <p className="text-sm text-slate-400 dark:text-slate-400 font-mono italic">No targets configured.</p>
                  ) : (
                    targets.map((t, i) => (
                      <div key={i} className="flex items-start justify-between border border-slate-100 dark:border-slate-700 p-3 bg-slate-50 dark:bg-slate-900">
                        <div className="flex flex-col">
                          <span className="font-bold text-primary dark:text-slate-300 text-sm uppercase tracking-wider mb-2 leading-none mt-1">{t.name}</span>
                          <div className="font-mono text-xs text-slate-600 dark:text-slate-200 flex items-center mt-1">
                            <span className="font-bold mr-2">IP:</span> {t.ip}
                            <span className="mx-3 text-gray-300">|</span>
                            <span className="font-bold mr-2">PORT:</span> {t.port}
                          </div>
                        </div>

                        <div className="flex items-start space-x-3 mt-1">
                          <div className="flex flex-col items-start mr-2">
                            <span className="text-[9px] font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-2 uppercase leading-none">Data Format</span>
                            <div className="flex items-center bg-gray-200 dark:bg-slate-700 rounded-sm overflow-hidden">
                              <button
                                onClick={() => t.format !== 'corrected' && handleToggleFormat(i)}
                                className={`px-2.5 py-1 text-[10px] font-bold tracking-wider transition-colors ${t.format === 'corrected' || !t.format
                                  ? 'bg-primary dark:bg-sky-600 text-white'
                                  : 'text-slate-500 dark:text-slate-300 hover:text-gray-700 dark:text-slate-200'
                                  }`}
                              >
                                m/s²
                              </button>
                              <button
                                onClick={() => t.format !== 'raw' && handleToggleFormat(i)}
                                className={`px-2.5 py-1 text-[10px] font-bold tracking-wider transition-colors ${t.format === 'raw'
                                  ? 'bg-amber-600 text-white'
                                  : 'text-slate-500 dark:text-slate-300 hover:text-gray-700 dark:text-slate-200'
                                  }`}
                              >
                                Counts
                              </button>
                            </div>
                          </div>

                          {t.ip !== '10.241.144.172' && (
                            <button onClick={() => handleRemoveTarget(i)} className="text-slate-400 dark:text-slate-400 hover:text-red-600 transition-colors -mt-0.5" title="Remove Target">
                              <X className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {/* Add Target Form */}
                <div className="shrink-0 space-y-4 pt-4 border-t border-slate-100 dark:border-slate-700/50 mt-auto">
                  <h4 className="text-xs font-bold text-slate-400 dark:text-slate-400 tracking-widest mb-2 shrink-0">Add New Data Forwarding IP</h4>
                  <div className="flex space-x-2 items-end bg-slate-50 dark:bg-slate-900 p-3 border border-slate-100 dark:border-slate-700">
                    <div className="flex-1">
                      <label className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-1">Name</label>
                      <input type="text" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Main Server" className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs h-[30px]" />
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-1">IP Address</label>
                      <input type="text" value={newIp} onChange={e => setNewIp(e.target.value)} placeholder="192.168.1.50" className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs h-[30px]" />
                    </div>
                    <div className="w-20">
                      <label className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-1">Port</label>
                      <input type="number" value={newPort} onChange={e => setNewPort(e.target.value)} className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-2 py-1.5 focus:outline-none focus:border-primary font-mono text-xs h-[30px]" />
                    </div>
                    
                    <div className="flex-shrink-0">
                      <label className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-1">Format</label>
                      <div className="flex items-center bg-gray-200 dark:bg-slate-700 rounded-md overflow-hidden h-[30px]">
                        <button
                          onClick={() => setNewFormat('corrected')}
                          className={`px-2 h-full text-[10px] font-bold tracking-wider transition-colors flex items-center justify-center ${newFormat === 'corrected' ? 'bg-primary dark:bg-sky-600 text-white' : 'text-slate-500 dark:text-slate-300 hover:text-gray-700 dark:text-slate-200'
                            }`}
                        >
                          m/s²
                        </button>
                        <button
                          onClick={() => setNewFormat('raw')}
                          className={`px-2 h-full text-[10px] font-bold tracking-wider transition-colors flex items-center justify-center ${newFormat === 'raw' ? 'bg-amber-600 text-white' : 'text-slate-500 dark:text-slate-300 hover:text-gray-700 dark:text-slate-200'
                            }`}
                        >
                          Counts
                        </button>
                      </div>
                    </div>

                    <button onClick={handleAddTarget} className="bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-300 px-3 flex items-center justify-center font-bold text-xs uppercase transition-colors h-[30px] rounded-md shrink-0">
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {targetError && <p className="text-[10px] font-bold text-red-500 font-mono mt-1">{targetError}</p>}

                  <button
                    onClick={handleSaveSettings}
                    className={`w-full text-white font-bold tracking-widest px-6 py-2 rounded-lg shadow-md flex items-center justify-center space-x-2 transition-all ${
                      hasUnsavedTargets 
                        ? 'bg-amber-500 hover:bg-amber-600 animate-pulse' 
                        : 'bg-primary dark:bg-sky-600 hover:bg-opacity-90 hover:shadow'
                    }`}
                  >
                    <Save className="w-4 h-4" />
                    <span>Save Targets</span>
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Tab 3: System */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'system' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full overflow-y-auto p-1 pb-6">
            {/* Left Column */}
            <div className="space-y-6 flex flex-col">

              {/* Data Storage Settings */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-fit">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0">
                  Data Storage
                </h3>
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-2">Data Storage Limit (days)</label>
                    <input
                      type="number"
                      value={retentionDays}
                      onChange={e => setRetentionDays(e.target.value)}
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                    <p className="text-xs text-slate-400 dark:text-slate-400 mt-2 font-mono">Older miniSEED files will be deleted.</p>
                  </div>

                  <div className="pt-2 border-t border-slate-100 dark:border-slate-700/50">
                    <span className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-1">Archive Size</span>
                    <span className="text-sm font-mono font-bold text-[#1a4162] dark:text-sky-300 bg-gray-100 dark:bg-slate-800 px-3 py-1 inline-block">
                      {(archiveSize / (1024 * 1024)).toFixed(2)} MB
                    </span>
                  </div>

                  <div className="flex justify-end pt-4 border-t border-slate-100 dark:border-slate-700/50">
                    <button
                      onClick={handleSaveSettings}
                      className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest px-6 py-2 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
                    >
                      <Save className="w-4 h-4" />
                      <span>Save Storage</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* UI Settings */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-fit">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0">
                  UI Settings
                </h3>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3 text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider">
                    {theme === 'dark' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
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
            </div>

            {/* Right Column: Calibration Settings & System Actions */}
            <div className="space-y-6">
              {/* Calibration Settings */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-fit">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0">
                  Calibration Settings
                </h3>
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-2">Calibration Time (seconds)</label>
                    <input
                      type="number"
                      value={calibrationTime}
                      onChange={e => setCalibrationTime(e.target.value)}
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                    />
                    <p className="text-xs text-slate-400 dark:text-slate-400 mt-2 font-mono">Recommended: 60 seconds</p>
                  </div>

                  <div className="flex justify-end pt-4 border-t border-slate-100 dark:border-slate-700/50">
                    <button
                      onClick={handleSaveSettings}
                      className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest px-6 py-2 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
                    >
                      <Save className="w-4 h-4" />
                      <span>Save Calibration</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* System Actions */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-fit">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0">
                  System Actions
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => requireAuth(() => openConfirmModal('restart'))}
                    className="bg-red-500 text-white font-bold tracking-widest px-4 py-3 flex flex-row items-center justify-center gap-2 hover:bg-red-700 transition-colors rounded-lg shadow-sm"
                  >
                    <Power className="w-4 h-4" />
                    <span className="text-xs">Restart Sensor</span>
                  </button>
                  <button
                    onClick={() => requireAuth(() => openConfirmModal('shutdown'))}
                    className="bg-red-500 text-white font-bold tracking-widest px-4 py-3 flex flex-row items-center justify-center gap-2 hover:bg-red-700 transition-colors rounded-lg shadow-sm"
                  >
                    <Power className="w-4 h-4" />
                    <span className="text-xs">Shutdown Sensor</span>
                  </button>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-mono text-center mt-4">This will disrupt telemetry until the system reboots.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tab 4: Security */}
        <div className={`absolute inset-0 transition-opacity duration-300 ${activeTab === 'security' ? 'opacity-100 z-10 pointer-events-auto' : 'opacity-0 z-0 pointer-events-none'}`}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full overflow-y-auto p-1 pb-6">
            {/* Left Column */}
            <div className="h-full flex flex-col">
              {/* ── Admin Password ─────────────────────────────────────────── */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-full">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0 gap-2">
                  Admin Password
                </h3>
                <div className="space-y-3 flex-1 flex flex-col">
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Current Password</label>
                    <div className="relative">
                      <input
                        type={showCurrentPw ? 'text' : 'password'}
                        value={currentPassword}
                        onChange={e => setCurrentPassword(e.target.value)}
                        placeholder="Current password"
                        className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm pr-10"
                      />
                      <button type="button" onClick={() => setShowCurrentPw(v => !v)} className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
                        {showCurrentPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">New Password</label>
                    <div className="relative">
                      <input
                        type={showNewPw ? 'text' : 'password'}
                        value={newPassword}
                        onChange={e => setNewPassword(e.target.value)}
                        placeholder="New password (minimum 4 characters)"
                        className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm pr-10"
                      />
                      <button type="button" onClick={() => setShowNewPw(v => !v)} className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
                        {showNewPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Confirm New Password</label>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      placeholder="Confirm new password"
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm"
                    />
                  </div>

                  {passwordStatus && (
                    <p className={`text-xs font-bold font-mono ${passwordStatus.isError ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-500'}`}>
                      {passwordStatus.isError ? '⚠ ' : '✓ '}{passwordStatus.msg}
                    </p>
                  )}

                  <div className="mt-auto pt-4 shrink-0">
                    <button
                      id="change-password-btn"
                      onClick={handleChangePassword}
                      className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest py-2 rounded-lg shadow-md flex items-center justify-center gap-2 hover:bg-opacity-90 transition-all text-sm"
                    >
                      Update Password
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column */}
            <div className="h-full flex flex-col">
              {/* ── Password Recovery ─────────────────────────────────────────── */}
              <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col h-full">
                <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 pb-2 border-b border-slate-100 dark:border-slate-700/50 flex items-center shrink-0 gap-2">
                  Password Recovery Questions
                </h3>

                {isRecoveryConfigured ? (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400 font-bold tracking-wide mb-4">
                    Password recovery is configured. You can update your questions below.
                  </p>
                ) : (
                  <p className="text-xs text-amber-600 dark:text-amber-500 font-bold tracking-wide mb-4">
                    Password recovery is not configured. Please set it up below to prevent getting locked out.
                  </p>
                )}

                <div className="space-y-3 flex-1 flex flex-col">
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Current Admin Password</label>
                    <input
                      type="password"
                      value={recoveryAuthPw}
                      onChange={e => setRecoveryAuthPw(e.target.value)}
                      placeholder="Required to set recovery questions"
                      className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Question 1</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={recoveryQ1}
                        onChange={e => setRecoveryQ1(e.target.value)}
                        className="flex-1 bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none text-sm"
                      />
                      <input
                        type="text"
                        value={recoveryA1}
                        onChange={e => setRecoveryA1(e.target.value)}
                        placeholder="Answer 1"
                        className="flex-1 bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-400 dark:text-slate-400 tracking-wider mb-1">Question 2</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={recoveryQ2}
                        onChange={e => setRecoveryQ2(e.target.value)}
                        className="flex-1 bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none text-sm"
                      />
                      <input
                        type="text"
                        value={recoveryA2}
                        onChange={e => setRecoveryA2(e.target.value)}
                        placeholder="Answer 2"
                        className="flex-1 bg-slate-100 dark:bg-slate-700 border-0 rounded-md focus:ring-1 focus:ring-slate-300 shadow-sm px-4 py-2 focus:outline-none font-mono text-sm"
                      />
                    </div>
                  </div>

                  {recoveryStatus && (
                    <p className={`text-xs font-bold font-mono ${recoveryStatus.isError ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-500'}`}>
                      {recoveryStatus.isError ? '⚠ ' : '✓ '}{recoveryStatus.msg}
                    </p>
                  )}

                  <div className="mt-auto pt-4 shrink-0">
                    <button
                      onClick={handleRecoverySetup}
                      className="w-full bg-primary dark:bg-sky-600 text-white font-bold tracking-widest py-2 rounded-lg shadow-md flex items-center justify-center gap-2 hover:bg-opacity-90 transition-all text-sm"
                    >
                      Save Recovery Questions
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Unified Confirm Modal (Restart / Shutdown) */}
      {confirmModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 p-6 max-w-sm w-full shadow-lg border border-slate-100 dark:border-slate-700 rounded-xl">
            <h3 className="text-lg font-bold mb-1 tracking-wide flex items-center text-red-600">
              <Power className="w-5 h-5 mr-2" />
              {confirmModal === 'shutdown' ? 'Shutdown Sensor' : 'Restart Sensor'}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 font-mono mb-6 leading-relaxed">
              {confirmModal === 'shutdown'
                ? 'Are you sure you want to power off the Sensor?'
                : 'Are you sure you want to reboot the Sensor? Telemetry will be temporarily unavailable.'}
            </p>
            <div className="flex space-x-3">
              <button
                onClick={closeConfirmModal}
                className="flex-1 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-bold tracking-wider py-2 rounded-lg transition-colors text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleSystemActionConfirm}
                className="flex-1 font-bold tracking-wider py-2 rounded-lg transition-colors text-sm text-white flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700"
              >
                {confirmModal === 'shutdown' ? 'Confirm Shutdown' : 'Confirm Restart'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Network Switch Modal — NON-DISMISSIBLE */}
      {switchModal && (
        <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-800 p-8 max-w-lg w-full shadow-2xl border border-slate-100 dark:border-slate-700">
            <div className="flex items-center justify-center mb-6">
              <div className="w-16 h-16 rounded-full bg-blue-50 border-2 border-blue-200 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary dark:text-slate-300" />
              </div>
            </div>
            <h3 className="text-lg font-bold text-[#1a4162] dark:text-sky-300 mb-3 uppercase tracking-wide text-center">
              Switching Network
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-200 mb-4 font-mono leading-relaxed text-center">
              Sensor is connecting to <strong className="text-[#1a4162] dark:text-sky-300">{switchModal.ssid}</strong>.
              Your connection to this dashboard will now be lost.
            </p>
            <div className="bg-amber-50 border border-amber-200 p-4 mb-4">
              <p className="text-xs font-bold text-amber-800 font-mono leading-relaxed text-center">
                Please connect this computer to <strong>"{switchModal.ssid}"</strong> and
                navigate to the sensor's new local IP address to regain access.
              </p>
            </div>
            <p className="text-[10px] text-slate-400 dark:text-slate-400 font-mono text-center uppercase tracking-wider">
              This modal will remain until the page is refreshed on the new network.
            </p>
          </div>
        </div>
      )}

      {/* Auth modal — rendered last so it sits above all other overlays */}
      <AuthModal
        isOpen={showAuthModal}
        onSuccess={handleAuthSuccess}
        onCancel={handleAuthCancel}
      />
    </div>
  );
}

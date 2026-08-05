import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircleIcon, MapPinIcon, ComputerDesktopIcon,
  CircleStackIcon, PlusIcon, ArrowRightIcon, ShieldCheckIcon
} from '@heroicons/react/24/solid';
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import { useTheme } from '../ThemeContext';
import { useTimeZone, TIMEZONES } from '../TimeZoneContext';
import { GlobeAltIcon } from '@heroicons/react/24/outline';

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

export default function Setup({ onComplete }) {
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const { timeZone, setTimeZone } = useTimeZone();

  // Data model
  const [formData, setFormData] = useState({
    device_name: 'CRISIS-NODE-01',
    device_id: '', // Will be generated
    owner_name: '',
    owner_email: '',
    latitude: '',
    longitude: '',
    elevation: '',
    floor_unit: 0,
    total_floors: 1,
    retention_days: 7,
    targets: [{ name: 'Crisislab Server', ip: '10.241.144.172', port: 2098, format: 'corrected' }]
  });

  // Additional target state
  const [newTarget, setNewTarget] = useState({ name: '', ip: '', port: 2098, format: 'corrected' });

  // Generate ID on mount
  useEffect(() => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let randomString = '';
    for (let i = 0; i < 4; i++) {
      randomString += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setFormData(prev => ({ ...prev, device_id: 'C' + randomString }));
  }, []);

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value
    }));
  };

  const handleTargetChange = (e) => {
    const { name, value, type } = e.target;
    setNewTarget(prev => ({
      ...prev,
      [name]: type === 'number' ? Number(value) : value
    }));
  };

  const handleAddTargetAndSubmit = async () => {
    if (newTarget.name && newTarget.ip) {
      const updatedTargets = [...formData.targets, { ...newTarget }];
      await submitConfig({ ...formData, targets: updatedTargets });
    } else {
      await submitConfig(formData);
    }
  };

  const submitConfig = async (dataToSubmit) => {
    setLoading(true);
    try {
      const payload = {
        ...dataToSubmit,
        is_configured: true,
        data_forwarding: true
      };

      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        localStorage.removeItem('has_seen_tour');
        onComplete();
      } else {
        alert('Failed to save configuration. Please try again.');
        setLoading(false);
      }
    } catch (err) {
      console.error(err);
      alert('Network error while saving configuration.');
      setLoading(false);
    }
  };

  const renderStepContent = () => {
    switch (step) {
      case 0: // Welcome
        return (
          <div className="text-center space-y-6">
            <div className="flex justify-center mb-8">
              <img src="/logo1.png" alt="CrisisLab Logo" className="h-32 object-contain" onError={(e) => e.target.style.display = 'none'} />
            </div>
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white">Welcome to CrisisLab</h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 max-w-xl mx-auto">
              Your Earthquake Early Warning (EEW) Sensor is almost ready.
              Let's walk through a few simple steps to configure your device for the network.
            </p>
            <div className="pt-6">
              <button
                onClick={() => setStep(1)}
                className="bg-amber-500 hover:bg-amber-600 text-white px-8 py-3 rounded-xl font-bold text-lg shadow-lg transition-all flex items-center mx-auto"
              >
                Get Started
                <ArrowRightIcon className="w-5 h-5 ml-2" />
              </button>
            </div>
          </div>
        );

      case 1: // General Info
        return (
          <div className="space-y-6 animate-fade-in">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">General Information</h2>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Set up the basic identity of your sensor node to help us manage it effectively.
                <span className="block mt-1 font-medium text-amber-600 dark:text-amber-400">Note: You can always change these settings later in the Sensor Control Panel.</span>
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-white dark:bg-slate-800 p-6 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Device Name</label>
                <input
                  type="text" name="device_name" value={formData.device_name} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Device ID</label>
                <input
                  type="text" value={formData.device_id} disabled
                  className="w-full bg-gray-100 dark:bg-slate-900/50 border border-gray-300 dark:border-slate-600 text-gray-500 dark:text-gray-400 text-sm rounded-lg block p-2.5 cursor-not-allowed font-mono"
                />
                <p className="text-xs text-gray-500 mt-1 flex items-center"><ShieldCheckIcon className="w-3 h-3 mr-1" /> Auto-generated unique identifier</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Owner Name</label>
                <input
                  type="text" name="owner_name" value={formData.owner_name} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Owner Email</label>
                <input
                  type="email" name="owner_email" value={formData.owner_email} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-gray-200 dark:border-slate-700">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Sensor Location</h2>
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Why accurate location matters</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Accurate latitude, longitude, and elevation are critical for triangulating seismic events rapidly and reliably.
                  <strong> Your exact location is securely processed and will not be shared publicly.</strong>
                </p>
              </div>
            </div>

            <div className="h-64 w-full border border-gray-100 dark:border-slate-700 rounded-xl z-0 relative overflow-hidden shadow-sm">
              <MapContainer center={[formData.latitude || 0, formData.longitude || 0]} zoom={2} scrollWheelZoom={true} style={{ height: '100%', width: '100%' }}>
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <LocationMarker
                  position={{ lat: formData.latitude, lng: formData.longitude }}
                  setPosition={(pos) => setFormData(prev => ({ ...prev, latitude: pos.lat, longitude: pos.lng }))}
                />
              </MapContainer>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-white dark:bg-slate-800 p-6 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Latitude</label>
                <input
                  type="number" step="any" name="latitude" value={formData.latitude} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Longitude</label>
                <input
                  type="number" step="any" name="longitude" value={formData.longitude} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Elevation (m)</label>
                <input
                  type="number" step="any" name="elevation" value={formData.elevation} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Floor Unit</label>
                <input
                  type="number" name="floor_unit" value={formData.floor_unit} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Total Floors</label>
                <input
                  type="number" name="total_floors" value={formData.total_floors} onChange={handleChange}
                  className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                />
              </div>
            </div>

            <div className="flex justify-between items-center pt-4">
              <span className="text-sm text-red-500 font-medium">
                {(!formData.device_name || !formData.owner_name || !formData.owner_email || formData.latitude === '' || formData.longitude === '' || formData.elevation === '') && "Please fill in all general information and location details to continue."}
              </span>
              <button
                onClick={() => setStep(2)}
                disabled={!formData.device_name || !formData.owner_name || !formData.owner_email || formData.latitude === '' || formData.longitude === '' || formData.elevation === ''}
                className="bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 dark:disabled:bg-slate-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
              >
                Next Step
              </button>
            </div>
          </div>
        );

      case 2: // Storage Limit & Timezone
        return (
          <div className="space-y-6 animate-fade-in">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Display Timezone</h2>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Select your preferred timezone for displaying dates and times across the dashboard.
              </p>
            </div>

            <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm">
              <select
                value={timeZone}
                onChange={(e) => setTimeZone(e.target.value)}
                className="w-full md:w-1/2 bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5 font-medium"
              >
                {TIMEZONES.map(tz => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>

            <div className="pt-4 border-t border-gray-200 dark:border-slate-700 mt-6">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Storage Limit</h2>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Storage is now user configurable and can be longer than 7 days, which is the default. We recommend a maximum of 21 days.
              </p>
            </div>

            <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm">
              <div className="flex items-center space-x-3 mb-5">
                <input
                  type="number" min="1" max="68" name="retention_days" value={formData.retention_days} onChange={handleChange}
                  className="w-24 bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5 font-medium"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">Days</span>
              </div>

              <div className="w-full">
                <p className="text-sm text-gray-700 dark:text-gray-300 font-bold mb-1">
                  Be careful when configuring this parameter!
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed max-w-3xl">
                  You risk filling up the disk space. By default we ship with a 16 GB micro SD card. We estimate free space for data storage is at 8-10 GB. At ~120 MB/day, the maximum storage limit is around<strong> 70 days</strong>.
                </p>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <button
                onClick={() => setStep(1)}
                className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white px-6 py-2 font-medium"
              >
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="bg-amber-500 hover:bg-amber-600 text-white px-6 py-2 rounded-lg font-medium transition-colors"
              >
                Next Step
              </button>
            </div>
          </div>
        );

      case 3: // Data Cast IP
        return (
          <div className="space-y-6 animate-fade-in">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Additional Data Cast</h2>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                Your sensor is already configured to transmit to the CrisisLab server. You may optionally forward data to a secondary IP.
                <span className="block mt-1 font-medium text-amber-600 dark:text-amber-400">Note: You can always edit or add more targets later from the Settings page.</span>
              </p>
            </div>

            <div className="bg-white dark:bg-slate-800 p-6 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm">
              <div className="flex items-center space-x-2 mb-6">
                <CheckCircleIcon className="w-5 h-5 text-green-500 shrink-0" />
                <p className="text-sm text-gray-600 dark:text-gray-400 font-medium">
                  CrisisLab Network Server (10.241.144.172:2098) is active and securely embedded.
                </p>
              </div>

              <div className="space-y-4">
                <h3 className="text-md font-semibold text-gray-800 dark:text-gray-200 border-b border-gray-200 dark:border-gray-700 pb-2">
                  Optional Secondary Destination
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 tracking-wider mb-1">Target Name</label>
                    <input
                      type="text" name="name" value={newTarget.name} onChange={handleTargetChange} placeholder="e.g. Local Server"
                      className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 tracking-wider mb-1">IP Address</label>
                    <input
                      type="text" name="ip" value={newTarget.ip} onChange={handleTargetChange} placeholder="192.168.1.100"
                      className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 tracking-wider mb-1">Port</label>
                    <input
                      type="number" name="port" value={newTarget.port} onChange={handleTargetChange}
                      className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 tracking-wider mb-1">Data Format</label>
                    <select
                      name="format" value={newTarget.format} onChange={handleTargetChange}
                      className="w-full bg-gray-50 dark:bg-slate-900 border border-gray-300 dark:border-slate-600 text-gray-900 dark:text-white text-sm rounded-lg focus:ring-amber-500 focus:border-amber-500 block p-2.5"
                    >
                      <option value="corrected">Corrected (m/s²)</option>
                      <option value="raw">Raw (ADC counts)</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-between items-center pt-4">
              <button
                onClick={() => setStep(2)}
                className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white px-6 py-2 font-medium"
              >
                Back
              </button>

              <div className="space-x-3">
                <button
                  onClick={() => submitConfig(formData)}
                  disabled={loading}
                  className="bg-gray-200 dark:bg-slate-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-slate-600 px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Skip
                </button>
                <button
                  onClick={handleAddTargetAndSubmit}
                  disabled={loading || (!newTarget.name && newTarget.ip) || (newTarget.name && !newTarget.ip)}
                  className="bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center inline-flex"
                >
                  {loading ? 'Saving...' : 'Finish Setup'}
                </button>
              </div>
            </div>
          </div>
        );
      default: return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-slate-950 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 font-sans">
      <div className="sm:mx-auto sm:w-full sm:max-w-2xl">
        {step > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between">
              {[1, 2, 3].map(i => (
                <div key={i} className="flex flex-col items-center relative z-10">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm transition-colors ${step >= i ? 'bg-amber-500 text-white' : 'bg-gray-300 dark:bg-slate-700 text-gray-500'}`}>
                    {step > i ? <CheckCircleIcon className="w-5 h-5 text-white" /> : i}
                  </div>
                  <span className={`text-xs mt-2 font-medium ${step >= i ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500'}`}>
                    {i === 1 ? 'General' : i === 2 ? 'Time & Storage' : 'Target'}
                  </span>
                </div>
              ))}
              <div className="absolute top-4 left-0 w-full h-1 bg-gray-300 dark:bg-slate-700 -z-10 mt-1 sm:max-w-2xl">
                <div
                  className="h-full bg-amber-500 transition-all duration-300"
                  style={{ width: `${(step - 1) * 50}%` }}
                ></div>
              </div>
            </div>
          </div>
        )}

        <div className={step > 0 ? "bg-white dark:bg-slate-900 py-8 px-4 shadow sm:rounded-2xl sm:px-10 border border-gray-100 dark:border-slate-800" : ""}>
          {renderStepContent()}
        </div>
      </div>
    </div>
  );
}

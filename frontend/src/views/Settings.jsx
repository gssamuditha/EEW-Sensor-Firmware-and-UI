import { useState, useEffect } from 'react';
import { Save, Plus, X } from 'lucide-react';

export default function Settings() {
  const [targets, setTargets] = useState([{ ip: '127.0.0.1', port: 2098 }]);
  const [newIp, setNewIp] = useState('');
  const [newPort, setNewPort] = useState(2098);
  const [lat, setLat] = useState(0.0);
  const [lon, setLon] = useState(0.0);
  const [status, setStatus] = useState('');

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (data.targets && data.targets.length > 0) setTargets(data.targets);
        setLat(data.latitude || 0.0);
        setLon(data.longitude || 0.0);
      })
      .catch(console.error);
  }, []);

  const handleAddTarget = () => {
    if (!newIp) return;
    setTargets([...targets, { ip: newIp, port: parseInt(newPort) }]);
    setNewIp('');
  };

  const handleRemoveTarget = (index) => {
    setTargets(targets.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          targets: targets,
          latitude: parseFloat(lat),
          longitude: parseFloat(lon)
        })
      });
      if (res.ok) {
        setStatus('Configuration saved successfully.');
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (e) {
      console.error(e);
      setStatus('Error saving configuration.');
    }
  };

  return (
    <div className="p-8 h-full bg-gray-50 flex flex-col overflow-y-auto">
      <h2 className="text-2xl font-bold text-primary tracking-wide mb-8 uppercase">System Configuration</h2>
      
      <div className="bg-white p-8 border border-gray-200 shadow-sm max-w-2xl mb-8">
        <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-6 pb-2 border-b border-gray-100">
          Sensor Location
        </h3>
        
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Latitude</label>
            <input 
              type="number" step="any"
              value={lat}
              onChange={e => setLat(e.target.value)}
              className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono"
            />
          </div>
          <div>
            <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Longitude</label>
            <input 
              type="number" step="any"
              value={lon}
              onChange={e => setLon(e.target.value)}
              className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono"
            />
          </div>
        </div>
      </div>

      <div className="bg-white p-8 border border-gray-200 shadow-sm max-w-2xl">
        <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-6 pb-2 border-b border-gray-100">
          UDP Target Servers
        </h3>
        
        <div className="space-y-6">
          
          {/* Target List */}
          <div className="space-y-2">
            {targets.length === 0 ? (
                <p className="text-sm text-gray-400 font-mono italic">No targets configured.</p>
            ) : (
                targets.map((t, i) => (
                  <div key={i} className="flex items-center justify-between border border-gray-200 p-3 bg-gray-50">
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

          {/* Add New Target Form */}
          <div className="flex space-x-4 items-end bg-gray-50 p-4 border border-gray-200">
            <div className="flex-1">
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">New IP</label>
              <input 
                type="text" 
                value={newIp}
                onChange={e => setNewIp(e.target.value)}
                className="w-full border border-gray-300 rounded-none px-3 py-2 focus:outline-none focus:border-primary font-mono text-sm"
                placeholder="192.168.1.100"
              />
            </div>
            <div className="w-32">
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">New Port</label>
              <input 
                type="number" 
                value={newPort}
                onChange={e => setNewPort(e.target.value)}
                className="w-full border border-gray-300 rounded-none px-3 py-2 focus:outline-none focus:border-primary font-mono text-sm"
              />
            </div>
            <button 
              onClick={handleAddTarget}
              className="bg-gray-200 text-gray-700 hover:bg-gray-300 hover:text-gray-900 px-4 py-2 flex items-center space-x-1 font-bold text-sm tracking-wider uppercase transition-colors"
            >
              <Plus size={16} />
              <span>Add</span>
            </button>
          </div>
          
          {status && (
            <div className={`p-3 text-sm font-bold font-mono ${status.includes('Error') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}`}>
              {status}
            </div>
          )}

          <button 
            onClick={handleSave}
            className="w-full bg-primary text-white font-bold tracking-widest uppercase py-3 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity"
          >
            <Save size={20} />
            <span>Save Configuration</span>
          </button>
        </div>
      </div>
    </div>
  );
}

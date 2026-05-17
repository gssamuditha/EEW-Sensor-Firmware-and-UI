import { useState, useRef } from 'react';
import LiveChart from '../components/LiveChart';

const TIMEZONES = [
  "UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo", "Asia/Colombo"
];

export default function Dashboard() {
  const [timeZone, setTimeZone] = useState('UTC');
  
  const zRef = useRef(null);
  const xRef = useRef(null);
  const yRef = useRef(null);

  const updateReadouts = (z, x, y) => {
    if (zRef.current) zRef.current.innerText = z.toFixed(4);
    if (xRef.current) xRef.current.innerText = x.toFixed(4);
    if (yRef.current) yRef.current.innerText = y.toFixed(4);
  };

  return (
    <div className="p-8 h-full flex flex-col bg-gray-50">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-primary tracking-wide">LIVE TELEMETRY</h2>
        <div className="flex items-center space-x-3 text-sm">
          <label className="font-bold text-gray-500 uppercase tracking-wider">Timezone</label>
          <select 
            value={timeZone} 
            onChange={(e) => setTimeZone(e.target.value)}
            className="border border-gray-300 rounded-none px-3 py-1.5 focus:outline-none focus:border-primary font-mono text-sm bg-white"
          >
            {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
      </div>
      
      <div className="flex-1 mb-6">
        <LiveChart timeZone={timeZone} updateReadouts={updateReadouts} />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <Readout label="ENZ (Vertical)" valueRef={zRef} unit="m/s²" color="text-red-600" />
        <Readout label="ENN (North)" valueRef={xRef} unit="m/s²" color="text-teal-600" />
        <Readout label="ENE (East)" valueRef={yRef} unit="m/s²" color="text-yellow-600" />
      </div>
    </div>
  );
}

function Readout({ label, valueRef, unit, color }) {
  return (
    <div className="bg-white border border-gray-200 p-6 flex flex-col items-center shadow-sm">
      <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">{label}</div>
      <div ref={valueRef} className={`text-4xl font-mono font-bold ${color}`}>
        0.0000
      </div>
      <div className="text-sm font-bold text-gray-300 mt-1 uppercase tracking-wider">{unit}</div>
    </div>
  );
}

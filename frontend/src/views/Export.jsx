import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import { useTimeZone } from '../TimeZoneContext';
import { format, fromZonedTime } from 'date-fns-tz';

export default function Export() {
  const { timeZone } = useTimeZone();

  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');

  // Update default start/end times when component mounts or timezone changes
  useEffect(() => {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    
    setStart(format(oneHourAgo, "yyyy-MM-dd'T'HH:mm", { timeZone }));
    setEnd(format(now, "yyyy-MM-dd'T'HH:mm", { timeZone }));
  }, [timeZone]);

  const handleExport = () => {
    if (!start || !end) {
      alert("Please select both start and end times.");
      return;
    }
    
    // Parse the local input string AS IF it were in the target timezone
    const startDate = fromZonedTime(start, timeZone);
    const endDate = fromZonedTime(end, timeZone);
    
    const startTime = startDate.getTime() / 1000;
    const endTime = endDate.getTime() / 1000;
    
    window.open(`/api/export?start=${startTime}&end=${endTime}`, '_blank');
  };

  return (
    <div className="p-8 h-full bg-gray-50 flex flex-col">
      <h2 className="text-2xl font-bold text-primary tracking-wide mb-8 uppercase">Data Export</h2>
      
      <div className="bg-white p-8 border border-gray-200 shadow-sm max-w-2xl">
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">Start Time</label>
            <input 
              type="datetime-local" 
              value={start}
              onChange={e => setStart(e.target.value)}
              className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono"
            />
          </div>
          
          <div>
            <label className="block text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">End Time</label>
            <input 
              type="datetime-local" 
              value={end}
              onChange={e => setEnd(e.target.value)}
              className="w-full border border-gray-300 rounded-none px-4 py-2 focus:outline-none focus:border-primary font-mono"
            />
          </div>
          
          <button 
            onClick={handleExport}
            className="w-full bg-primary text-white font-bold tracking-widest uppercase py-3 flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-opacity"
          >
            <Download size={20} />
            <span>Export CSV</span>
          </button>
        </div>
      </div>
    </div>
  );
}

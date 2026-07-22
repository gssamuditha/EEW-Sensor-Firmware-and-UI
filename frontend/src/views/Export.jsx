import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import { useTimeZone } from '../TimeZoneContext';
import { format, fromZonedTime } from 'date-fns-tz';

export default function Export() {
  const { timeZone } = useTimeZone();

  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [formatType, setFormatType] = useState('csv');

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
    
    window.open(`/api/export?start=${startTime}&end=${endTime}&format=${formatType}`, '_blank');
  };

  return (
    <div className="p-8 h-full bg-slate-50 dark:bg-slate-900 flex flex-col">
      <h2 className="text-2xl font-bold text-primary dark:text-blue-400 tracking-wide mb-8 uppercase">Data Export</h2>
      
      <div className="bg-white dark:bg-slate-800 p-8 border border-slate-100 dark:border-slate-700/50 shadow-md rounded-xl max-w-2xl">
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Start Time</label>
            <input 
              type="datetime-local" 
              value={start}
              onChange={e => setStart(e.target.value)}
              className="w-full bg-slate-100 dark:bg-slate-800/80 border-0 rounded-md px-4 py-2 text-slate-600 dark:text-slate-300 font-semibold focus:outline-none focus:ring-1 focus:ring-slate-300 font-mono shadow-sm"
            />
          </div>
          
          <div>
            <label className="block text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">End Time</label>
            <input 
              type="datetime-local" 
              value={end}
              onChange={e => setEnd(e.target.value)}
              className="w-full bg-slate-100 dark:bg-slate-800/80 border-0 rounded-md px-4 py-2 text-slate-600 dark:text-slate-300 font-semibold focus:outline-none focus:ring-1 focus:ring-slate-300 font-mono shadow-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Export Format</label>
            <select
              value={formatType}
              onChange={e => setFormatType(e.target.value)}
              className="w-full bg-slate-100 dark:bg-slate-800/80 border-0 rounded-md px-4 py-2 text-slate-600 dark:text-slate-300 font-semibold focus:outline-none focus:ring-1 focus:ring-slate-300 font-mono shadow-sm cursor-pointer"
            >
              <option value="csv">CSV Format</option>
              <option value="mseed">miniSEED Format (ZIP archive)</option>
            </select>
            {formatType === 'mseed' && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-2">
                Downloads a ZIP file containing one miniSEED file per channel, structured following the SeisComP Data Structure (SDS) naming convention.
              </p>
            )}
          </div>
          
          <button 
            onClick={handleExport}
            className="w-full bg-primary dark:bg-blue-600 text-white font-bold tracking-widest uppercase py-3 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
          >
            <Download size={20} />
            <span>Export {formatType.toUpperCase()}</span>
          </button>
        </div>
      </div>
      
      <div className="bg-white dark:bg-slate-800 p-8 border border-slate-100 dark:border-slate-700/50 shadow-md rounded-xl max-w-2xl mt-8">
        <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-4">Full Archive Backup</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mb-6">
          Download a complete backup of the SDS miniSEED archive. This includes all historical data currently saved on the device.
        </p>
        <button 
          onClick={() => window.open('/api/export/all', '_blank')}
          className="w-full bg-amber-600 text-white font-bold tracking-widest uppercase py-3 rounded-lg shadow-md flex items-center justify-center space-x-2 hover:bg-opacity-90 transition-all hover:shadow"
        >
          <Download size={20} />
          <span>Download All Archive Data (ZIP)</span>
        </button>
      </div>
    </div>
  );
}

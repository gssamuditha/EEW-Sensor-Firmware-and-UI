import { useState, useEffect } from 'react';
import { ArrowDownTrayIcon as Download, DocumentTextIcon as FileText, ChartBarIcon as Activity, CircleStackIcon as Database, ArrowDownOnSquareIcon as Save } from '@heroicons/react/24/solid';
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

  const timeLabelBadge = `(${timeZone})`;

  return (
    <div className="p-3 md:p-6 h-full flex flex-col bg-slate-50 dark:bg-slate-900 overflow-y-auto lg:overflow-hidden">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-primary dark:text-sky-400 tracking-wide">Data Export</h2>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-2 pb-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-6xl">

          {/* Custom Range Export Widget */}
          <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col">
            <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-5 flex items-center shrink-0">
              <FileText fill="currentColor" className="w-4 h-4 mr-2" /> Custom Range Export
            </h3>

            <div className="space-y-5 flex-1">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="tour-export-start">
                  <label className="flex items-center text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wide mb-1.5">
                    Start Time <span className="ml-1 text-slate-400 dark:text-slate-400/70 font-normal">{timeLabelBadge}</span>
                  </label>
                  <input
                    type="datetime-local"
                    value={start}
                    onChange={e => setStart(e.target.value)}
                    className="w-full h-9 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-3 text-xs text-slate-600 dark:text-slate-200 font-semibold focus:outline-none focus:ring-1 focus:ring-primary/50 shadow-sm font-mono dark:[color-scheme:dark]"
                  />
                </div>
                <div className="tour-export-end">
                  <label className="flex items-center text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wide mb-1.5">
                    End Time <span className="ml-1 text-slate-400 dark:text-slate-400/70 font-normal">{timeLabelBadge}</span>
                  </label>
                  <input
                    type="datetime-local"
                    value={end}
                    onChange={e => setEnd(e.target.value)}
                    className="w-full h-9 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-3 text-xs text-slate-600 dark:text-slate-200 font-semibold focus:outline-none focus:ring-1 focus:ring-primary/50 shadow-sm font-mono dark:[color-scheme:dark]"
                  />
                </div>
              </div>

              <div className="tour-export-format">
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-300 tracking-wide mb-1.5">Format</label>
                <select
                  value={formatType}
                  onChange={e => setFormatType(e.target.value)}
                  className="w-full h-9 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-3 text-xs text-slate-600 dark:text-slate-200 font-semibold focus:outline-none focus:ring-1 focus:ring-primary/50 shadow-sm cursor-pointer"
                >
                  <option value="csv">CSV</option>
                  <option value="mseed">miniSEED</option>
                </select>
                {formatType === 'mseed' && (
                  <p className="text-[10px] text-slate-400 dark:text-slate-400 font-mono mt-2 leading-relaxed">
                    Downloads a ZIP file containing one miniSEED file per channel
                  </p>
                )}
              </div>
            </div>

            <div className="tour-export-submit pt-5 mt-auto">
              <button
                onClick={handleExport}
                className="w-full bg-primary dark:bg-sky-600 hover:bg-opacity-90 text-white font-bold tracking-wider text-xs py-2.5 rounded-lg shadow-sm flex items-center justify-center space-x-2 transition-all"
              >
                <Download fill="currentColor" className="w-3.5 h-3.5" />
                <span>EXPORT DATA</span>
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-6">
            {/* Full Archive Backup Widget */}
            <div className="tour-export-archive bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col">
              <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 flex items-center shrink-0">
                <Database fill="currentColor" className="w-4 h-4 mr-2" /> Full Archive Backup
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-300 font-mono mb-5 leading-relaxed">
                Download a complete backup of the SDS miniSEED archive. This includes all historical data currently saved on the device.
              </p>
              <button
                onClick={() => window.open('/api/export/all', '_blank')}
                className="w-full mt-auto bg-amber-600 hover:bg-amber-700 text-white font-bold tracking-wider text-xs py-2.5 rounded-lg shadow-sm flex items-center justify-center space-x-2 transition-all"
              >
                <Download fill="currentColor" className="w-4 h-4" />
                <span>DOWNLOAD ARCHIVE (ZIP)</span>
              </button>
            </div>

            {/* Device Response File Widget */}
            <div className="tour-export-response bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 p-6 shadow-md rounded-xl flex flex-col">
              <h3 className="text-sm font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-4 flex items-center shrink-0">
                <Activity fill="currentColor" className="w-4 h-4 mr-2" /> Device Response File
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-300 font-mono mb-5 leading-relaxed">
                Download the <strong>StationXML</strong> instrument response file for this sensor.
                Required when a UDP target is set to <strong>Raw Counts</strong> mode
              </p>
              <a
                href="/api/metadata/stationxml"
                download
                className="w-full mt-auto bg-slate-700 dark:bg-sky-600 hover:bg-slate-800 dark:hover:bg-sky-500 text-white font-bold tracking-wider text-xs py-2.5 rounded-lg shadow-sm flex items-center justify-center space-x-2 transition-all"
              >
                <Save fill="currentColor" className="w-3.5 h-3.5" />
                <span>DOWNLOAD STATIONXML</span>
              </a>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

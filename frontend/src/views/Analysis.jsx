import { useState, useEffect, useCallback, useMemo } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import FilteredChart from '../components/FilteredChart';
import { useTimeZone } from '../TimeZoneContext';

// Quick-select durations (minutes)
const QUICK_OPTIONS = [
  { label: '5 min',  value: 5 },
  { label: '15 min', value: 15 },
  { label: '30 min', value: 30 },
  { label: '1 hour', value: 60 },
];

// Convert epoch seconds to local datetime-local string (minute precision)
function epochToLocal(epoch, tz) {
  const d = new Date(epoch * 1000);
  // Format as YYYY-MM-DDTHH:mm in the target timezone
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(d);
  const get = (type) => (parts.find(p => p.type === type) || {}).value || '';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

// Convert local datetime-local string to epoch seconds
function localToEpoch(dtStr, tz) {
  // datetime-local gives "YYYY-MM-DDTHH:mm"
  // We need to interpret this in the user's timezone
  const d = new Date(dtStr);
  return d.getTime() / 1000;
}

// Round epoch down to the nearest minute
function floorMinute(epoch) {
  return Math.floor(epoch / 60) * 60;
}


export default function Analysis() {
  const { timeZone } = useTimeZone();

  // --- Filter state ---
  const [lowHz, setLowHz] = useState(0.1);
  const [highHz, setHighHz] = useState(20.0);
  const [activeFilter, setActiveFilter] = useState(null);
  const [filterStatus, setFilterStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [filterVersion, setFilterVersion] = useState(0);

  // --- Filter presets ---
  const [presets, setPresets] = useState({});
  const [activePreset, setActivePreset] = useState(null);

  // --- Time range state ---
  const nowEpoch = () => Math.floor(Date.now() / 1000);
  const [startEpoch, setStartEpoch] = useState(() => floorMinute(nowEpoch() - 300));
  const [endEpoch, setEndEpoch] = useState(() => floorMinute(nowEpoch()));
  const [isLive, setIsLive] = useState(true); // true = end time tracks "now"

  // --- Data availability ---
  const [availability, setAvailability] = useState(null);

  // --- UI state ---
  const [isControlsExpanded, setIsControlsExpanded] = useState(true);

  // Fetch filter, presets, and availability on mount
  useEffect(() => {
    const base = `${window.location.protocol}//${window.location.host}`;

    fetch(`${base}/api/analysis/filter`)
      .then(r => r.json())
      .then(data => {
        setLowHz(data.low_hz);
        setHighHz(data.high_hz);
        setActiveFilter(data);
        setFilterStatus('active');
      })
      .catch(() => setFilterStatus('error'));

    fetch(`${base}/api/analysis/presets`)
      .then(r => r.json())
      .then(data => setPresets(data.presets || {}))
      .catch(() => {});

    fetch(`${base}/api/analysis/availability`)
      .then(r => r.json())
      .then(data => setAvailability(data))
      .catch(() => {});
  }, []);

  // When switching to live mode, snap the end time to now.
  // We DO NOT update this continuously, otherwise it triggers massive
  // historical data re-fetches every tick. FilteredChart handles the live tail.
  useEffect(() => {
    if (!isLive) return;
    setEndEpoch(nowEpoch());
  }, [isLive]);

  // Duration in minutes
  const durationMinutes = useMemo(() => {
    return Math.round((endEpoch - startEpoch) / 60);
  }, [startEpoch, endEpoch]);

  // Validate duration
  const durationError = useMemo(() => {
    if (durationMinutes < 5) return 'Minimum duration is 5 minutes';
    if (durationMinutes > 60) return 'Maximum duration is 1 hour';
    return null;
  }, [durationMinutes]);

  // Apply filter
  const applyFilter = useCallback(() => {
    setErrorMsg('');
    if (lowHz >= highHz) {
      setErrorMsg('Low frequency must be less than high frequency');
      return;
    }
    const base = `${window.location.protocol}//${window.location.host}`;
    setFilterStatus('updating');
    fetch(`${base}/api/analysis/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ low_hz: lowHz, high_hz: highHz }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Failed'); });
        return r.json();
      })
      .then(data => {
        setActiveFilter(data);
        setFilterStatus('active');
        setFilterVersion(v => v + 1);
      })
      .catch(e => {
        setErrorMsg(e.message);
        setFilterStatus('error');
      });
  }, [lowHz, highHz]);

  // Apply preset
  const applyPreset = useCallback((key) => {
    const preset = presets[key];
    if (!preset) return;
    setLowHz(preset.low_hz);
    setHighHz(preset.high_hz);
    setActivePreset(key);
    // Also apply immediately
    setErrorMsg('');
    const base = `${window.location.protocol}//${window.location.host}`;
    setFilterStatus('updating');
    fetch(`${base}/api/analysis/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ low_hz: preset.low_hz, high_hz: preset.high_hz }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Failed'); });
        return r.json();
      })
      .then(data => {
        setActiveFilter(data);
        setFilterStatus('active');
        setFilterVersion(v => v + 1);
      })
      .catch(e => {
        setErrorMsg(e.message);
        setFilterStatus('error');
      });
  }, [presets]);

  // Quick select: set start = now - minutes, end = now, go live
  const quickSelect = useCallback((minutes) => {
    const now = nowEpoch();
    setStartEpoch(now - minutes * 60);
    setEndEpoch(now);
    setIsLive(true);
  }, []);

  // Handle start time change
  const handleStartChange = (e) => {
    const epoch = localToEpoch(e.target.value, timeZone);
    if (!isNaN(epoch)) {
      setStartEpoch(floorMinute(epoch));
    }
  };

  // Handle end time change
  const handleEndChange = (e) => {
    const epoch = localToEpoch(e.target.value, timeZone);
    if (!isNaN(epoch)) {
      setEndEpoch(floorMinute(epoch));
      setIsLive(false);
    }
  };

  // Toggle live mode
  const toggleLive = () => {
    if (!isLive) {
      // Switch to live: set end to now
      const now = nowEpoch();
      setEndEpoch(now);
      // Adjust start if window too large
      if (now - startEpoch > 3600) {
        setStartEpoch(now - 3600);
      }
    }
    setIsLive(!isLive);
  };

  // Min datetime for the picker (24 hours ago or earliest data)
  const minDatetime = useMemo(() => {
    const twentyFourHoursAgo = nowEpoch() - 86400;
    const earliest = availability?.earliest || twentyFourHoursAgo;
    return epochToLocal(Math.max(earliest, twentyFourHoursAgo), timeZone);
  }, [availability, timeZone]);

  const maxDatetime = useMemo(() => {
    return epochToLocal(nowEpoch(), timeZone);
  }, [timeZone]);

  // Format duration for display
  const durationStr = useMemo(() => {
    const mins = durationMinutes;
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
  }, [durationMinutes]);

  // Check if custom low/high match any preset
  useEffect(() => {
    let matched = null;
    for (const [key, preset] of Object.entries(presets)) {
      if (Math.abs(preset.low_hz - lowHz) < 0.001 && Math.abs(preset.high_hz - highHz) < 0.001) {
        matched = key;
        break;
      }
    }
    setActivePreset(matched);
  }, [lowHz, highHz, presets]);

  return (
    <div className="p-6 h-full flex flex-col bg-slate-50 dark:bg-slate-900 overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-center mb-4 flex-shrink-0">
        <div className="flex items-center space-x-3">
          <h2 className="text-xl font-bold text-primary dark:text-blue-400 tracking-wide">SIGNAL ANALYSIS</h2>
          {activeFilter && filterStatus === 'active' && (
            <div className="px-3 py-1 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-bold rounded-md border border-slate-100 dark:border-slate-700 shadow-sm flex items-center space-x-2">
              <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
              <span>BANDPASS {activeFilter.low_hz}–{activeFilter.high_hz} Hz</span>
            </div>
          )}
          {filterStatus === 'updating' && (
            <div className="px-3 py-1 bg-white dark:bg-slate-800 text-yellow-600 text-xs font-bold rounded border border-yellow-200 shadow-sm">
              Updating filter…
            </div>
          )}
        </div>
        <button 
          onClick={() => setIsControlsExpanded(!isControlsExpanded)}
          className="flex items-center space-x-1.5 text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-3 py-1.5 rounded-md shadow-sm transition-colors"
        >
          {isControlsExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          <span>{isControlsExpanded ? 'HIDE FILTERS' : 'SHOW FILTERS'}</span>
        </button>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-3">
        {/* Controls Row */}
        <div className={`bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl shadow-md flex-shrink-0 transition-all duration-300 ease-in-out overflow-hidden ${isControlsExpanded ? 'opacity-100 max-h-[500px]' : 'opacity-0 max-h-0 border-0 shadow-none'}`}>
          <div className="p-4 grid grid-cols-1 xl:grid-cols-[auto_1fr] gap-6 items-end">
            {/* Left: Time Range */}
            <div className="flex flex-col gap-3">
              {/* Top Row: Start & End */}
              <div className="flex items-end gap-3">
                {/* Start time */}
                <div className="flex flex-col">
                  <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Start</label>
                  <input
                    type="datetime-local"
                    value={epochToLocal(startEpoch, timeZone)}
                    onChange={handleStartChange}
                    min={minDatetime}
                    max={maxDatetime}
                    className="h-8 border-0 bg-slate-100 dark:bg-slate-800/80 rounded-md px-3 text-xs font-mono font-semibold text-slate-600 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-slate-300 shadow-sm"
                  />
                </div>

                <span className="text-slate-300 font-bold text-xs pb-2">→</span>

                {/* End time */}
                <div className="flex flex-col">
                  <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">End</label>
                  <input
                    type="datetime-local"
                    value={epochToLocal(endEpoch, timeZone)}
                    onChange={handleEndChange}
                    min={minDatetime}
                    max={maxDatetime}
                    disabled={isLive}
                    className={`h-8 border-0 bg-slate-100 dark:bg-slate-800/80 rounded-md px-3 text-xs font-mono font-semibold text-slate-600 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-slate-300 shadow-sm ${isLive ? 'opacity-50 cursor-not-allowed' : ''}`}
                  />
                </div>
              </div>

              {/* Bottom Row: Live, Duration, Quick Selects */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={toggleLive}
                  className={`h-8 px-3 rounded-md text-[10px] font-bold tracking-wider transition-all shadow-sm border ${
                    isLive
                      ? 'bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600'
                      : 'bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-600 hover:border-emerald-400 hover:text-emerald-600'
                  }`}
                >
                  {isLive ? '● LIVE' : 'NOW'}
                </button>

                <div className={`h-8 flex items-center px-3 rounded-md text-[10px] font-bold font-mono border ${
                  durationError
                    ? 'bg-red-50 text-red-500 border-red-200'
                    : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700/50'
                }`}>
                  {durationStr}
                </div>

                {QUICK_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => quickSelect(opt.value)}
                    className="h-8 px-2.5 rounded-md text-[10px] font-bold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors border-0 shadow-sm"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Right: Bandpass Filter */}
            <div className="flex flex-col gap-3 xl:ml-auto">
              {/* Top Row: Presets */}
              {Object.keys(presets).length > 0 && (
                <div className="flex flex-col">
                  <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Presets</label>
                  <div className="flex items-center gap-1.5">
                    {Object.entries(presets).map(([key, preset]) => (
                      <button
                        key={key}
                        onClick={() => applyPreset(key)}
                        title={`${preset.low_hz}–${preset.high_hz} Hz`}
                        className={`h-8 px-2.5 rounded-md text-[10px] font-bold transition-all shadow-sm border-0 ${
                          activePreset === key
                            ? 'bg-primary dark:bg-blue-600 text-white'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                        }`}
                      >
                        {preset.label.split(' ')[0]}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Bottom Row: Low, High, Apply */}
              <div className="flex items-end gap-5">
                {/* Low Frequency */}
                <div className="flex flex-col">
                  <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Low (Hz)</label>
                  <div className="flex items-center space-x-1.5">
                    <input
                      type="range" min="0.01" max="10" step="0.01"
                      value={lowHz}
                      onChange={e => { setLowHz(parseFloat(e.target.value)); setActivePreset(null); }}
                      className="w-16 sm:w-20 accent-primary"
                    />
                    <input
                      type="number" min="0.01" max="10" step="0.01"
                      value={lowHz}
                      onChange={e => { setLowHz(parseFloat(e.target.value) || 0.01); setActivePreset(null); }}
                      className="h-8 w-14 bg-slate-100 dark:bg-slate-800/80 border-0 rounded-md px-1.5 text-xs font-mono font-semibold text-center focus:outline-none focus:ring-1 focus:ring-slate-300 shadow-sm"
                    />
                  </div>
                </div>

                {/* High Frequency */}
                <div className="flex flex-col">
                  <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">High (Hz)</label>
                  <div className="flex items-center space-x-1.5">
                    <input
                      type="range" min="0.5" max="50" step="0.5"
                      value={highHz}
                      onChange={e => { setHighHz(parseFloat(e.target.value)); setActivePreset(null); }}
                      className="w-16 sm:w-20 accent-primary"
                    />
                    <input
                      type="number" min="0.5" max="50" step="0.5"
                      value={highHz}
                      onChange={e => { setHighHz(parseFloat(e.target.value) || 0.5); setActivePreset(null); }}
                      className="h-8 w-14 bg-slate-100 dark:bg-slate-800/80 border-0 rounded-md px-1.5 text-xs font-mono font-semibold text-center focus:outline-none focus:ring-1 focus:ring-slate-300 shadow-sm"
                    />
                  </div>
                </div>

                {/* Apply Button */}
                <button
                  onClick={applyFilter}
                  className="h-8 bg-primary dark:bg-blue-600 hover:bg-opacity-90 text-white rounded-md font-bold transition-all shadow-md px-4 text-[10px] tracking-wider"
                >
                  APPLY FILTER
                </button>
              </div>
            </div>
            
            {/* Error message */}
            {(errorMsg || durationError) && (
              <div className="col-span-1 xl:col-span-2 text-[10px] text-red-500 font-bold mt-[-8px]">
                {errorMsg} {durationError}
              </div>
            )}
          </div>
        </div>

        {/* Filtered Waveform Charts */}
        <div className="flex-1 min-h-0 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md flex flex-col overflow-hidden">
          {durationError ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">
              {durationError}. Adjust the time range above.
            </div>
          ) : (
            <FilteredChart
              timeZone={timeZone}
              startEpoch={startEpoch}
              endEpoch={endEpoch}
              isLive={isLive}
              filterVersion={filterVersion}
            />
          )}
        </div>
      </div>
    </div>
  );
}

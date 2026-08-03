import { useState, useEffect, useCallback, useMemo } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import FilteredChart from '../components/FilteredChart';
import { useTimeZone } from '../TimeZoneContext';
import { formatInTimeZone, fromZonedTime } from 'date-fns-tz';

// Quick-select durations (minutes)
const QUICK_OPTIONS = [
  { label: '5 min', value: 5 },
  { label: '15 min', value: 15 },
  { label: '30 min', value: 30 },
  { label: '1 hour', value: 60 },
];

// Convert epoch seconds to local datetime-local string (minute precision)
function epochToLocal(epoch, tz) {
  return formatInTimeZone(new Date(epoch * 1000), tz, "yyyy-MM-dd'T'HH:mm");
}

// Convert local datetime-local string to epoch seconds
function localToEpoch(dtStr, tz) {
  // datetime-local gives "YYYY-MM-DDTHH:mm"
  // We need to interpret this in the user's timezone
  const d = fromZonedTime(dtStr, tz);
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
  const [startEpoch, setStartEpoch] = useState(() => floorMinute(nowEpoch() - 1800));
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
      .catch(() => { });

    fetch(`${base}/api/analysis/availability`)
      .then(r => r.json())
      .then(data => setAvailability(data))
      .catch(() => { });
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

  // Check if current filter settings differ from active filter
  const isFilterDirty = useMemo(() => {
    if (!activeFilter) return false;
    return Math.abs(lowHz - activeFilter.low_hz) > 0.001 || Math.abs(highHz - activeFilter.high_hz) > 0.001;
  }, [lowHz, highHz, activeFilter]);

  // Apply filter
  const applyFilter = useCallback(() => {
    setErrorMsg('');
    if (lowHz >= highHz) {
      setErrorMsg('Low frequency must be less than high frequency');
      return;
    }

    // If live, snap the time window to 'now' so the historical fetch doesn't
    // request an old time window, which would create a gap between the fetch
    // end time and the new WebSocket data.
    if (isLive) {
      const now = nowEpoch();
      const delta = now - endEpoch;
      if (delta > 0) {
        setStartEpoch(s => s + delta);
        setEndEpoch(now);
      }
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
  }, [lowHz, highHz, isLive, endEpoch]);

  // Apply preset
  const applyPreset = useCallback((key) => {
    const preset = presets[key];
    if (!preset) return;
    setLowHz(preset.low_hz);
    setHighHz(preset.high_hz);
    setActivePreset(key);
    // User must explicitly click "APPLY FILTER" to apply these changes
  }, [presets]);

  // Quick select: behavior depends on isLive
  const quickSelect = useCallback((minutes) => {
    if (isLive) {
      const now = nowEpoch();
      setStartEpoch(now - minutes * 60);
      setEndEpoch(now);
    } else {
      setEndEpoch(startEpoch + minutes * 60);
    }
  }, [isLive, startEpoch]);

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

  // Min datetime for the picker — use the archive's actual earliest timestamp.
  // Falls back to 7 days ago if archive availability is not yet loaded.
  const minDatetime = useMemo(() => {
    const sevenDaysAgo = nowEpoch() - 7 * 86400;
    const earliest = availability?.earliest || sevenDaysAgo;
    return epochToLocal(earliest, timeZone);
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
    <div className="p-3 md:p-6 h-full flex flex-col bg-slate-50 dark:bg-slate-900 overflow-y-auto lg:overflow-hidden">
      {/* Header & Controls */}
      <div className="flex flex-col xl:flex-row xl:justify-between items-start w-full gap-4 mb-4 flex-shrink-0">
        {/* Left Column (Title + Filter Presets) */}
        <div className="flex flex-col gap-2">
          {/* Top: Title & Badge */}
          <div className="flex flex-row items-center gap-3">
            <h1 className="text-3xl font-bold text-primary dark:text-sky-400 tracking-wide">Signal Analysis</h1>
            {activeFilter && filterStatus === 'active' && (
              <div className="px-2 py-1 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-200 text-[10px] font-bold rounded-md border border-slate-100 dark:border-slate-700 shadow-sm flex items-center space-x-1.5">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                <span>BANDPASS {activeFilter.low_hz}–{activeFilter.high_hz} Hz</span>
              </div>
            )}
            {filterStatus === 'updating' && (
              <div className="px-2 py-1 bg-white dark:bg-slate-800 text-yellow-600 text-[10px] font-bold rounded border border-yellow-200 shadow-sm">
                Updating filter…
              </div>
            )}
          </div>


        </div>

        {/* Right Column (Stacked Boxes) */}
        <div className="flex flex-col items-end gap-2">
          {/* Top Box: Time Settings */}
          <div className="flex flex-row items-end gap-2 flex-wrap">
            <button
              onClick={toggleLive}
              className={`h-7 px-2.5 rounded-md text-[9px] font-bold tracking-wider shadow-sm border ${isLive ? 'bg-emerald-500 text-white border-emerald-500 hover:bg-emerald-600' : 'bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-300 border-slate-200 dark:border-slate-600 hover:text-emerald-600'
                }`}
            >
              {isLive ? '● LIVE' : 'NOW'}
            </button>
            <div className="flex flex-col">
              <label className="text-[8px] font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-0.5">
                Start <span className="ml-0.5 text-slate-400 font-normal">({timeZone})</span>
              </label>
              <input
                type="datetime-local"
                value={epochToLocal(startEpoch, timeZone)}
                onChange={handleStartChange}
                onClick={() => isLive && setIsLive(false)}
                min={minDatetime}
                max={maxDatetime}
                className={`h-7 border-0 bg-white dark:bg-slate-700 rounded-md px-2 text-[10px] font-mono font-semibold text-slate-600 dark:text-slate-200 shadow-sm border border-slate-200 dark:border-slate-700 focus:ring-1 focus:ring-slate-300 dark:[color-scheme:dark] ${isLive ? 'opacity-50 cursor-pointer' : ''}`}
              />
            </div>
            <span className="text-slate-300 font-bold text-[10px] pb-1.5">→</span>
            <div className="flex flex-col">
              <label className="text-[8px] font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-0.5">
                End <span className="ml-0.5 text-slate-400 font-normal">({timeZone})</span>
              </label>
              <input
                type="datetime-local"
                value={epochToLocal(endEpoch, timeZone)}
                onChange={handleEndChange}
                onClick={() => isLive && setIsLive(false)}
                min={minDatetime}
                max={maxDatetime}
                readOnly={isLive}
                className={`h-7 border-0 bg-white dark:bg-slate-700 rounded-md px-2 text-[10px] font-mono font-semibold text-slate-600 dark:text-slate-200 shadow-sm border border-slate-200 dark:border-slate-700 focus:ring-1 focus:ring-slate-300 dark:[color-scheme:dark] ${isLive ? 'opacity-50 cursor-pointer' : ''}`}
              />
            </div>
            <div className={`h-7 flex items-center px-2 rounded-md text-[9px] font-bold font-mono border ${durationError ? 'bg-red-50 text-red-500 border-red-200' : 'bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-300 border-slate-200 dark:border-slate-700/50'
              }`}>
              {durationStr}
            </div>
            {QUICK_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => quickSelect(opt.value)}
                className="h-7 px-2 rounded-md text-[9px] font-bold text-slate-500 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 shadow-sm transition-colors"
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Bottom Box: Frequency Sliders + Apply Button */}
          <div className="flex flex-row items-end gap-2 w-full justify-between flex-wrap mt-1">
            {Object.keys(presets).length > 0 && (
              <div className="flex flex-col flex-1 min-w-[120px] mr-2">
                <label className="text-[8px] font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-0.5">Preset</label>
                <select
                  value={activePreset || ''}
                  onChange={(e) => applyPreset(e.target.value)}
                  className="h-7 w-full bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-2 text-[10px] font-bold text-slate-600 dark:text-slate-200 shadow-sm focus:ring-1 focus:ring-slate-300 cursor-pointer"
                >
                  <option value="" disabled>Custom</option>
                  {Object.entries(presets).map(([key, preset]) => (
                    <option key={key} value={key}>{preset.label}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Frequency Controls & Apply Button */}
            <div className="flex flex-row items-end gap-2 flex-wrap ml-auto">
              <div className="flex flex-col w-[130px]">
                <label className="text-[8px] font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-0.5">Low (Hz)</label>
                <div className="flex items-center space-x-1.5 w-full">
                  <input type="range" min="0.01" max="10" step="0.01" value={lowHz} onChange={e => { setLowHz(parseFloat(e.target.value)); setActivePreset(null); }} className="flex-1 min-w-[80px] accent-primary" />
                  <input type="number" min="0.01" max="10" step="0.01" value={lowHz} onChange={e => { setLowHz(parseFloat(e.target.value) || 0.01); setActivePreset(null); }} className="h-7 w-12 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-1 text-[10px] font-mono font-semibold text-center focus:ring-1 focus:outline-none focus:ring-slate-300 shadow-sm" />
                </div>
              </div>
              <div className="flex flex-col w-[130px]">
                <label className="text-[8px] font-bold text-slate-500 dark:text-slate-300 tracking-wider mb-0.5">High (Hz)</label>
                <div className="flex items-center space-x-1.5 w-full">
                  <input type="range" min="0.5" max="50" step="0.5" value={highHz} onChange={e => { setHighHz(parseFloat(e.target.value)); setActivePreset(null); }} className="flex-1 min-w-[80px] accent-primary" />
                  <input type="number" min="0.5" max="50" step="0.5" value={highHz} onChange={e => { setHighHz(parseFloat(e.target.value) || 0.5); setActivePreset(null); }} className="h-7 w-12 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-md px-1 text-[10px] font-mono font-semibold text-center focus:ring-1 focus:outline-none focus:ring-slate-300 shadow-sm" />
                </div>
              </div>
              <button
                onClick={applyFilter}
                className={isFilterDirty
                  ? "h-7 bg-amber-500 hover:bg-amber-600 text-white rounded-md font-bold transition-all shadow-md px-4 text-[9px] tracking-wider shrink-0 animate-pulse border border-amber-400"
                  : "h-7 bg-primary dark:bg-sky-600 hover:bg-opacity-90 text-white rounded-md font-bold transition-all shadow-md px-4 text-[9px] tracking-wider shrink-0"
                }
              >
                Apply Filter
              </button>
            </div>
          </div>

          {(errorMsg || durationError) && (
            <div className="text-[9px] text-red-500 font-bold w-full text-right mt-[-4px]">
              {errorMsg} {durationError}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-3">

        {/* Filtered Waveform Charts */}
        <div className="flex-1 min-h-0 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md flex flex-col overflow-hidden">
          <div className="flex items-center justify-between mb-2 flex-shrink-0">
            <div />
            {availability?.earliest && (
              <span className="text-[9px] text-slate-400 dark:text-slate-500 font-mono">
                Archive from {new Date(availability.earliest * 1000).toLocaleDateString()}
              </span>
            )}
          </div>
          {durationError ? (
            <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-400 text-sm">
              {durationError}. Adjust the time range above.
            </div>
          ) : (
            <FilteredChart
              timeZone={timeZone}
              startEpoch={startEpoch}
              endEpoch={endEpoch}
              isLive={isLive}
              filterVersion={filterVersion}
              onError={setErrorMsg}
            />
          )}
        </div>
      </div>
    </div>
  );
}

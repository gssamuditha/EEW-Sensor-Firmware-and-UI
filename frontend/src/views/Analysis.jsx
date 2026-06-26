import { useState, useEffect, useCallback } from 'react';
import FilteredChart from '../components/FilteredChart';
import { useTimeZone } from '../TimeZoneContext';

const WINDOW_OPTIONS = [
  { label: '1 min', value: 1 },
  { label: '2 min', value: 2 },
  { label: '5 min', value: 5 },
  { label: '10 min', value: 10 },
  { label: '30 min', value: 30 },
  { label: '1 hour', value: 60 },
  { label: '2 hours', value: 120 },
  { label: '6 hours', value: 360 },
  { label: '12 hours', value: 720 },
  { label: '24 hours', value: 1440 },
];

export default function Analysis() {
  const { timeZone } = useTimeZone();

  // Filter state
  const [lowHz, setLowHz] = useState(0.1);
  const [highHz, setHighHz] = useState(20.0);
  const [windowMinutes, setWindowMinutes] = useState(1);
  const [activeFilter, setActiveFilter] = useState(null);
  const [filterStatus, setFilterStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState('');
  // Incremented on every successful filter apply — triggers FilteredChart re-fetch
  const [filterVersion, setFilterVersion] = useState(0);

  // Fetch current filter on mount
  useEffect(() => {
    const protocol = window.location.protocol;
    const host = window.location.host;
    fetch(`${protocol}//${host}/api/analysis/filter`)
      .then(r => r.json())
      .then(data => {
        setLowHz(data.low_hz);
        setHighHz(data.high_hz);
        setActiveFilter(data);
        setFilterStatus('active');
      })
      .catch(() => setFilterStatus('error'));
  }, []);

  const applyFilter = useCallback(() => {
    setErrorMsg('');
    if (lowHz >= highHz) {
      setErrorMsg('Low frequency must be less than high frequency');
      return;
    }
    const protocol = window.location.protocol;
    const host = window.location.host;
    setFilterStatus('updating');
    fetch(`${protocol}//${host}/api/analysis/filter`, {
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
        // Bump version to trigger FilteredChart to re-fetch with new filter
        setFilterVersion(v => v + 1);
      })
      .catch(e => {
        setErrorMsg(e.message);
        setFilterStatus('error');
      });
  }, [lowHz, highHz]);

  return (
    <div className="p-6 h-full flex flex-col bg-gray-50 overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-center mb-4 flex-shrink-0">
        <div className="flex items-center space-x-3">
          <h2 className="text-xl font-bold text-primary tracking-wide">SIGNAL ANALYSIS</h2>
          {activeFilter && filterStatus === 'active' && (
            <div className="px-3 py-1 bg-white text-gray-600 text-xs font-bold rounded border border-gray-200 shadow-sm flex items-center space-x-2">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span>BANDPASS {activeFilter.low_hz}–{activeFilter.high_hz} Hz</span>
            </div>
          )}
          {filterStatus === 'updating' && (
            <div className="px-3 py-1 bg-white text-yellow-600 text-xs font-bold rounded border border-yellow-200 shadow-sm">
              Updating filter…
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col gap-4">
        {/* Filter Control Card */}
        <div className="bg-white border border-gray-200 p-4 shadow-sm flex-shrink-0">
          <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Bandpass Filter Configuration</div>
          <div className="flex flex-wrap items-end gap-6">
            {/* Low Frequency */}
            <div className="flex flex-col">
              <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Low Cutoff (Hz)</label>
              <div className="flex items-center space-x-2">
                <input
                  type="range"
                  id="analysis-low-hz-slider"
                  min="0.01"
                  max="10"
                  step="0.01"
                  value={lowHz}
                  onChange={e => setLowHz(parseFloat(e.target.value))}
                  className="w-32 accent-primary"
                />
                <input
                  type="number"
                  id="analysis-low-hz-input"
                  min="0.01"
                  max="10"
                  step="0.01"
                  value={lowHz}
                  onChange={e => setLowHz(parseFloat(e.target.value) || 0.01)}
                  className="w-20 border border-gray-300 rounded px-2 py-1 text-sm font-mono text-center focus:outline-none focus:border-primary"
                />
              </div>
            </div>

            {/* High Frequency */}
            <div className="flex flex-col">
              <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">High Cutoff (Hz)</label>
              <div className="flex items-center space-x-2">
                <input
                  type="range"
                  id="analysis-high-hz-slider"
                  min="0.5"
                  max="50"
                  step="0.5"
                  value={highHz}
                  onChange={e => setHighHz(parseFloat(e.target.value))}
                  className="w-32 accent-primary"
                />
                <input
                  type="number"
                  id="analysis-high-hz-input"
                  min="0.5"
                  max="50"
                  step="0.5"
                  value={highHz}
                  onChange={e => setHighHz(parseFloat(e.target.value) || 0.5)}
                  className="w-20 border border-gray-300 rounded px-2 py-1 text-sm font-mono text-center focus:outline-none focus:border-primary"
                />
              </div>
            </div>

            {/* Time Window */}
            <div className="flex flex-col">
              <label className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">Time Window</label>
              <select
                id="analysis-time-window"
                value={windowMinutes}
                onChange={e => setWindowMinutes(parseInt(e.target.value))}
                className="border border-gray-300 rounded px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-primary bg-white shadow-sm"
              >
                {WINDOW_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {/* Apply Button */}
            <button
              id="analysis-apply-filter"
              onClick={applyFilter}
              className="bg-primary hover:bg-opacity-90 text-white rounded font-bold transition-colors shadow-sm px-4 py-1.5 text-xs tracking-wider"
            >
              APPLY FILTER
            </button>

            {/* Filter info */}
            {activeFilter && (
              <div className="text-[10px] text-gray-400 font-mono ml-auto self-center">
                Order: {activeFilter.order} · Fs: {activeFilter.fs} Hz · Butterworth IIR
              </div>
            )}
          </div>

          {/* Error message */}
          {errorMsg && (
            <div className="mt-2 text-xs text-red-500 font-bold">{errorMsg}</div>
          )}
        </div>

        {/* Filtered Waveform Charts */}
        <div className="flex-1 min-h-0 bg-white border border-gray-200 p-4 shadow-sm flex flex-col overflow-hidden">
          <FilteredChart
            timeZone={timeZone}
            timeWindowMinutes={windowMinutes}
            filterVersion={filterVersion}
          />
        </div>
      </div>
    </div>
  );
}

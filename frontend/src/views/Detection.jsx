import { useState, useEffect, useRef, useCallback } from 'react';
import { useTimeZone } from '../TimeZoneContext';
import { formatInTimeZone } from 'date-fns-tz';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtTime(epochSec, tz) {
  if (!epochSec) return '—';
  return formatInTimeZone(new Date(epochSec * 1000), tz, 'yyyy-MM-dd HH:mm:ss.SSS');
}

function fmtAmp(val) {
  if (val == null) return '—';
  return (val * 1e6).toFixed(3) + ' μm/s²';
}

function fmtRatio(v) {
  if (v == null) return '—';
  return Number(v).toFixed(3);
}

// STA/LTA ratio gauge needle
function RatioGauge({ ratio, threshold, label, unit }) {
  const pct = Math.min((ratio / (threshold * 2)) * 100, 100);
  const triggered = ratio >= threshold;
  const color = triggered ? '#ef4444' : ratio >= threshold * 0.75 ? '#f59e0b' : '#10b981';

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[10px] font-bold tracking-wider">
        <span className="text-slate-500 dark:text-slate-400 uppercase">{label}</span>
        <span style={{ color }} className="font-mono">{fmtRatio(ratio)}</span>
      </div>
      <div className="relative h-2.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
        {/* Threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-red-400/70 z-10"
          style={{ left: `${Math.min((threshold / (threshold * 2)) * 100, 99)}%` }}
        />
        {/* Fill bar */}
        <div
          className="h-full rounded-full transition-all duration-150"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// Animated waveform bars for "active listening" state
function PulseWave({ active }) {
  const heights = [4, 8, 12, 16, 20, 16, 12, 8, 4, 8, 12, 6, 10, 14, 18, 14];
  return (
    <div className="flex items-end gap-[3px] h-6">
      {heights.map((h, i) => (
        <div
          key={i}
          className="w-1 rounded-sm transition-all"
          style={{
            height: active ? `${h}px` : '3px',
            backgroundColor: active ? '#3b82f6' : '#94a3b8',
            animationDelay: `${i * 60}ms`,
            animation: active ? `pulse-bar 1.2s ease-in-out infinite alternate` : 'none',
            animationDelay: active ? `${i * 75}ms` : '0ms',
          }}
        />
      ))}
      <style>{`
        @keyframes pulse-bar {
          0%   { transform: scaleY(0.4); opacity: 0.6; }
          100% { transform: scaleY(1.0); opacity: 1.0; }
        }
      `}</style>
    </div>
  );
}

// ─── Event Row ────────────────────────────────────────────────────────────────

function EventRow({ ev, tz }) {
  const ratio = ev.notes?.match(/STA\/LTA=([\d.]+)/)?.[1];
  return (
    <tr className="border-b border-slate-100 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
      <td className="px-3 py-2 font-mono text-[11px] text-slate-600 dark:text-slate-300 whitespace-nowrap">
        {fmtTime(ev.detected_at, tz)}
      </td>
      <td className="px-3 py-2 text-center">
        <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400 tracking-widest">
          P-WAVE
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-slate-600 dark:text-slate-300 text-center">
        {ratio ? parseFloat(ratio).toFixed(2) : '—'}
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-slate-600 dark:text-slate-300 text-center uppercase">
        {ev.channel || '—'}
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-slate-600 dark:text-slate-300 text-right">
        {fmtAmp(ev.max_amplitude)}
      </td>
    </tr>
  );
}

// ─── Settings Panel ───────────────────────────────────────────────────────────

function DetectionSettings({ current, onSaved }) {
  const [form, setForm] = useState({
    sta_sec: current?.sta_sec ?? 0.5,
    lta_sec: current?.lta_sec ?? 10.0,
    threshold_on: current?.threshold_on ?? 3.5,
    threshold_off: current?.threshold_off ?? 1.5,
    detect_low_hz: 2.0,
    detect_high_hz: 15.0,
    detection_enabled: current?.enabled ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  // Sync when parent receives new status
  useEffect(() => {
    if (current) {
      setForm(f => ({
        ...f,
        sta_sec: current.sta_sec,
        lta_sec: current.lta_sec,
        threshold_on: current.threshold_on,
        threshold_off: current.threshold_off,
        detection_enabled: current.enabled,
      }));
    }
  }, [current?.sta_sec, current?.lta_sec]);

  const field = (key, label, min, max, step, unit) => (
    <div className="flex flex-col gap-1">
      <label className="text-[9px] font-bold text-slate-500 dark:text-slate-400 tracking-widest uppercase">
        {label} <span className="text-slate-400 font-normal normal-case">({unit})</span>
      </label>
      <div className="flex items-center gap-2">
        <input
          type="range" min={min} max={max} step={step} value={form[key]}
          onChange={e => setForm(f => ({ ...f, [key]: parseFloat(e.target.value) }))}
          className="flex-1 accent-blue-500"
        />
        <input
          type="number" min={min} max={max} step={step} value={form[key]}
          onChange={e => setForm(f => ({ ...f, [key]: parseFloat(e.target.value) || min }))}
          className="w-16 h-7 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-md px-2 text-[10px] font-mono font-semibold text-center focus:outline-none focus:ring-1 focus:ring-blue-400 shadow-sm"
        />
      </div>
    </div>
  );

  const save = async () => {
    setSaving(true); setMsg('');
    try {
      const r = await fetch('/api/detection/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!r.ok) {
        const d = await r.json();
        throw new Error(d.detail || 'Failed');
      }
      setMsg('Saved and applied ✓');
      onSaved && onSaved();
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-700 dark:text-slate-200 tracking-wide">Detection Parameters</h2>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400">ENABLED</span>
          <div
            onClick={() => setForm(f => ({ ...f, detection_enabled: !f.detection_enabled }))}
            className={`relative w-9 h-5 rounded-full transition-colors cursor-pointer ${form.detection_enabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'}`}
          >
            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${form.detection_enabled ? 'left-[18px]' : 'left-0.5'}`} />
          </div>
        </label>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {field('sta_sec', 'STA Window', 0.1, 5.0, 0.1, 's')}
        {field('lta_sec', 'LTA Window', 5.0, 60.0, 0.5, 's')}
        {field('threshold_on', 'Trigger ON Threshold', 1.5, 10.0, 0.1, 'ratio')}
        {field('threshold_off', 'De-trigger Threshold', 0.5, 5.0, 0.1, 'ratio')}
        {field('detect_low_hz', 'Pre-filter Low Cut', 0.5, 10.0, 0.5, 'Hz')}
        {field('detect_high_hz', 'Pre-filter High Cut', 5.0, 45.0, 1.0, 'Hz')}
      </div>

      <div className="flex items-center justify-between flex-wrap gap-2 pt-1 border-t border-slate-100 dark:border-slate-700/50">
        {msg && (
          <span className={`text-[10px] font-bold ${msg.startsWith('Error') ? 'text-red-500' : 'text-emerald-500'}`}>
            {msg}
          </span>
        )}
        <button
          onClick={save}
          disabled={saving}
          className="ml-auto h-7 px-5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-[9px] font-bold tracking-widest shadow transition-colors disabled:opacity-50"
        >
          {saving ? 'SAVING…' : 'APPLY'}
        </button>
      </div>
    </div>
  );
}

// ─── Main Detection Page ──────────────────────────────────────────────────────

export default function Detection() {
  const { timeZone } = useTimeZone();
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [liveEvents, setLiveEvents] = useState([]);   // WS trigger_on events
  const [wsConnected, setWsConnected] = useState(false);
  const [alertFlash, setAlertFlash] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const wsRef = useRef(null);
  const statusIntervalRef = useRef(null);
  const alertTimerRef = useRef(null);

  // ── Fetch status poll ──
  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/detection/status');
      if (r.ok) setStatus(await r.json());
    } catch {}
  }, []);

  // ── Fetch event log ──
  const fetchEvents = useCallback(async () => {
    try {
      const r = await fetch('/api/events?limit=50');
      if (r.ok) {
        const d = await r.json();
        setEvents(d.events || []);
      }
    } catch {}
  }, []);

  // ── WebSocket to /ws/detection ──
  const connectWS = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/detection`);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => {
      setWsConnected(false);
      setTimeout(connectWS, 3000);   // auto-reconnect
    };
    ws.onerror = () => ws.close();

    ws.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data);
        if (ev.type === 'trigger_on') {
          // Flash alert and prepend to live feed
          setAlertFlash(true);
          clearTimeout(alertTimerRef.current);
          alertTimerRef.current = setTimeout(() => setAlertFlash(false), 5000);

          setLiveEvents(prev => [{ ...ev, _id: Date.now() }, ...prev].slice(0, 20));
          // Also refresh the persistent event log
          fetchEvents();
        } else if (ev.type === 'trigger_off') {
          fetchEvents();  // update duration/maxAmp
        }
      } catch {}
    };
  }, [fetchEvents]);

  useEffect(() => {
    fetchStatus();
    fetchEvents();
    connectWS();

    statusIntervalRef.current = setInterval(fetchStatus, 1000);

    return () => {
      clearInterval(statusIntervalRef.current);
      clearTimeout(alertTimerRef.current);
      wsRef.current?.close();
    };
  }, [fetchStatus, fetchEvents, connectWS]);

  const ratios = status?.ratios || {};
  const threshOn = status?.threshold_on || 3.5;
  const isTriggered = status?.triggered || false;
  const ltaReady = status?.lta_ready !== false;
  const ltaFillPct = status?.lta_fill_pct ?? 0;
  const ltaSec = status?.lta_sec ?? 10;
  const remainSec = ltaReady ? 0 : Math.ceil((ltaSec * 0.9) * (1 - ltaFillPct / 100));

  return (
    <div className="p-3 md:p-6 h-full flex flex-col bg-slate-50 dark:bg-slate-900 overflow-y-auto gap-4">

      {/* ── Alert Flash Banner ── */}
      {alertFlash && (
        <div className="flex-shrink-0 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500 text-white shadow-xl animate-bounce">
          <span className="text-xl">⚠️</span>
          <div>
            <p className="font-bold text-sm tracking-wide">P-WAVE DETECTED</p>
            <p className="text-xs opacity-80">STA/LTA threshold exceeded — possible seismic arrival</p>
          </div>
          <button onClick={() => setAlertFlash(false)} className="ml-auto opacity-70 hover:opacity-100 text-lg">✕</button>
        </div>
      )}

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-blue-600 dark:text-blue-400 tracking-wide">P-Wave Detection</h1>
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[9px] font-bold tracking-widest border
            ${isTriggered
              ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 border-red-200 dark:border-red-700 animate-pulse'
              : ltaReady
                ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-700'
                : 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-600 dark:text-yellow-400 border-yellow-200 dark:border-yellow-700'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isTriggered ? 'bg-red-500 animate-ping' : ltaReady ? 'bg-emerald-500' : 'bg-yellow-500'}`} />
            {isTriggered ? 'TRIGGERED' : ltaReady ? 'MONITORING' : 'WARMING UP'}
          </div>
          <div className={`flex items-center gap-1 px-2 py-1 rounded-md text-[9px] font-bold border
            ${wsConnected
              ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-700'
              : 'bg-slate-100 dark:bg-slate-700 text-slate-400 border-slate-200 dark:border-slate-600'}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-blue-500' : 'bg-slate-400'}`} />
            {wsConnected ? 'LIVE' : 'DISCONNECTED'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PulseWave active={ltaReady && !isTriggered} />
          <button
            onClick={() => setShowSettings(s => !s)}
            className="h-8 px-3 rounded-md text-[9px] font-bold tracking-widest border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 shadow-sm transition-colors"
          >
            ⚙ PARAMETERS
          </button>
        </div>
      </div>

      {/* ── Settings Panel (collapsible) ── */}
      {showSettings && (
        <DetectionSettings
          current={status}
          onSaved={() => { fetchStatus(); setShowSettings(false); }}
        />
      )}

      {/* ── STA/LTA Ratio Gauges + Status Cards ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-shrink-0">

        {/* Composite + channel gauges */}
        <div className="lg:col-span-2 bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-slate-600 dark:text-slate-300 tracking-widest uppercase">STA/LTA Ratios</h2>
            {!ltaReady && (
              <div className="flex flex-col items-end gap-1">
                <span className="text-[9px] text-yellow-500 font-bold">
                  LTA FILLING… {ltaFillPct.toFixed(0)}% (~{remainSec}s)
                </span>
                <div className="w-40 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-yellow-400 rounded-full transition-all duration-500"
                    style={{ width: `${ltaFillPct}%` }}
                  />
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3">
            {/* Composite */}
            <div className="pb-3 mb-1 border-b border-slate-100 dark:border-slate-700/50">
              <RatioGauge
                ratio={ratios.composite || 0}
                threshold={threshOn}
                label="Composite (Vector Norm²)"
                unit=""
              />
            </div>
            {/* Per-channel */}
            {Object.entries(ratios)
              .filter(([k]) => k !== 'composite')
              .map(([ch, val]) => (
                <RatioGauge key={ch} ratio={val} threshold={threshOn} label={ch} unit="" />
              ))}
          </div>
        </div>

        {/* Status cards column */}
        <div className="flex flex-col gap-3">
          {/* Trigger state */}
          <div className={`rounded-xl p-4 shadow-md border flex-1 flex flex-col items-center justify-center gap-2 transition-all
            ${isTriggered
              ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-700'
              : 'bg-emerald-50 dark:bg-emerald-900/10 border-emerald-100 dark:border-emerald-800'}`}
          >
            <div className={`text-5xl select-none transition-all ${isTriggered ? 'animate-bounce' : ''}`}>
              {isTriggered ? '🔴' : '🟢'}
            </div>
            <p className={`text-sm font-bold tracking-wide ${isTriggered ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
              {isTriggered ? 'TRIGGERED' : 'QUIET'}
            </p>
            <p className="text-[9px] text-slate-500 dark:text-slate-400 text-center">
              {isTriggered ? 'P-wave onset detected' : 'No seismic activity'}
            </p>
          </div>

          {/* Threshold info card */}
          <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md">
            <p className="text-[9px] font-bold text-slate-500 dark:text-slate-400 tracking-widest mb-2 uppercase">Algorithm</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[10px]">
              {[
                ['STA', `${status?.sta_sec ?? '—'}s`],
                ['LTA', `${status?.lta_sec ?? '—'}s`],
                ['ON', fmtRatio(status?.threshold_on)],
                ['OFF', fmtRatio(status?.threshold_off)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-slate-400 dark:text-slate-500 font-bold">{k}</span>
                  <span className="font-mono text-slate-700 dark:text-slate-200">{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Last event mini-card */}
          {status?.last_event && (
            <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl p-4 shadow-md">
              <p className="text-[9px] font-bold text-slate-500 dark:text-slate-400 tracking-widest mb-2 uppercase">
                {status.last_event.type === 'trigger_on' ? 'Last Trigger ON' : 'Last Trigger OFF'}
              </p>
              <p className="font-mono text-[10px] text-slate-700 dark:text-slate-200">
                {fmtTime(status.last_event.timestamp, timeZone)}
              </p>
              {status.last_event.ratio != null && (
                <p className="text-[9px] text-slate-500 dark:text-slate-400 mt-1">
                  ratio = <span className="font-mono font-bold text-blue-500">{fmtRatio(status.last_event.ratio)}</span>
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Live Trigger Feed ── */}
      {liveEvents.length > 0 && (
        <div className="bg-white dark:bg-slate-800 border border-red-100 dark:border-red-800/40 rounded-xl p-4 shadow-md flex-shrink-0">
          <h2 className="text-xs font-bold text-red-600 dark:text-red-400 tracking-widest uppercase mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
            Live Trigger Events (this session)
          </h2>
          <div className="flex flex-col gap-2">
            {liveEvents.map(ev => (
              <div key={ev._id} className="flex items-center gap-3 text-[11px] font-mono bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2 border border-red-100 dark:border-red-800/30">
                <span className="text-red-500 font-bold">⚡ TRIGGER ON</span>
                <span className="text-slate-500 dark:text-slate-400">{fmtTime(ev.timestamp, timeZone)}</span>
                <span className="ml-auto text-slate-700 dark:text-slate-200">ratio <b className="text-red-500">{fmtRatio(ev.ratio)}</b></span>
                <span className="text-slate-500 dark:text-slate-400">{ev.triggered_channel}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Persistent Event Log Table ── */}
      <div className="bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700/50 rounded-xl shadow-md flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700/50 flex-shrink-0">
          <h2 className="text-xs font-bold text-slate-600 dark:text-slate-300 tracking-widest uppercase">
            Seismic Event Log
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-slate-400 font-mono">{events.length} records</span>
            <button
              onClick={fetchEvents}
              className="h-6 px-2 rounded text-[9px] font-bold border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-500 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
            >
              ↺ REFRESH
            </button>
          </div>
        </div>

        <div className="overflow-auto flex-1">
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 h-48 text-slate-400 dark:text-slate-500">
              <span className="text-5xl select-none">📋</span>
              <p className="text-sm font-medium">No events recorded yet</p>
              <p className="text-[11px]">Detections will appear here once the LTA window fills (~{status?.lta_sec ?? 10}s after startup)</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-700/50 sticky top-0 z-10">
                  {['Detected At', 'Type', 'STA/LTA', 'Channel', 'Peak Amplitude'].map(h => (
                    <th key={h} className="px-3 py-2 text-[9px] font-bold text-slate-500 dark:text-slate-400 tracking-widest uppercase whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {events.map(ev => (
                  <EventRow key={ev.id} ev={ev} tz={timeZone} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

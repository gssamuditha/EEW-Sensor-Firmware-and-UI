import { useEffect, useRef, useState, useCallback } from 'react';
import {
  TimeLine,
  timeAxisPlugin,
  valueAxisPlugin,
  pointerCrosshairPlugin,
  highlightNearestPointPlugin,
} from '@crisislab/timeline';

/**
 * FilteredChart — Hybrid historical + real-time filtered waveform charts.
 *
 * 1. On mount / window change: fetches historical data from /api/analysis/window
 * 2. Connects to /ws/analysis for real-time filtered data (live tail)
 * 3. Uses stable refs so TimeLine sees data mutations correctly
 */

const CHANNELS = ['ENZ', 'ENN', 'ENE'];

// ---------------------------------------------------------------------------
// Cursor sync (shared across all analysis chart instances)
// ---------------------------------------------------------------------------
const analysisCursorSync = {
  charts: [],
  register(chart) { this.charts.push(chart); },
  unregister(chart) { this.charts = this.charts.filter(c => c !== chart); },
  plugin() {
    let syncX = -1;
    return {
      _setSyncX(x) { syncX = x; },
      _clearSyncX() { syncX = -1; },
      construct: (chart) => { analysisCursorSync.register(chart); },
      'draw:after': (chart) => {
        if (chart.helpfulInfo.cursor.overChart) {
          const myX = chart.helpfulInfo.cursor.chartX;
          analysisCursorSync.charts.forEach(other => {
            if (other !== chart) {
              const p = other.plugins.find(p => p && typeof p._setSyncX === 'function');
              if (p) p._setSyncX(myX);
            }
          });
        } else {
          analysisCursorSync.charts.forEach(other => {
            if (other !== chart) {
              const p = other.plugins.find(p => p && typeof p._clearSyncX === 'function');
              if (p) p._clearSyncX();
            }
          });
        }
        if (syncX >= 0 && !chart.helpfulInfo.cursor.overChart) {
          const ctx = chart.ctx;
          ctx.save();
          ctx.strokeStyle = 'rgba(100, 100, 100, 0.5)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(syncX, chart.padding.top);
          ctx.lineTo(syncX, chart.padding.top + chart.heightInsidePadding);
          ctx.stroke();
          ctx.restore();
        }
      },
    };
  },
};

// ---------------------------------------------------------------------------
// AnalysisChannelPlot — single TimeLine chart per axis
// ---------------------------------------------------------------------------
function AnalysisChannelPlot({ channelName, timeZone, dataRef, latestValue, tick, timeWindowMs }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = new TimeLine({
      container: containerRef.current,
      data: dataRef.current[channelName],    // TimeLine holds this reference permanently
      timeWindow: timeWindowMs,
      timeAxisLabel: '',
      valueAxisLabel: '',
      lineWidth: 1.2,
      plugins: [
        timeAxisPlugin((x) => {
          try {
            return new Intl.DateTimeFormat('en-US', {
              timeZone, hour12: false,
              hour: 'numeric', minute: '2-digit', second: '2-digit'
            }).format(new Date(x));
          } catch { return ''; }
        }),
        valueAxisPlugin((v) => v.toFixed(4)),
        pointerCrosshairPlugin(),
        highlightNearestPointPlugin(),
        analysisCursorSync.plugin(),
      ],
    });
    chart.foregroundColour = '#374151';
    chart.backgroundColour = '#ffffff';
    chartRef.current = chart;

    return () => {
      analysisCursorSync.unregister(chart);
      if (containerRef.current) containerRef.current.innerHTML = '';
    };
  }, [timeZone, channelName]); // Note: NOT timeWindowMs — we update it dynamically below

  // Recompute on tick (data was mutated in-place on the same array ref)
  useEffect(() => {
    if (chartRef.current) chartRef.current.recompute();
  }, [tick]);

  // Update timeWindow dynamically without recreating the chart
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.timeWindow = timeWindowMs;
      chartRef.current.recompute();
    }
  }, [timeWindowMs]);

  const labelColor = (name) => {
    if (name.includes('Z')) return 'text-red-600';
    if (name.includes('N')) return 'text-teal-600';
    return 'text-yellow-600';
  };

  return (
    <div className="flex flex-col flex-1 min-h-[100px] mb-[2px] bg-white shadow-sm p-1 rounded">
      <div className="flex items-center justify-between mb-0 px-1">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-gray-500 text-[10px] tracking-widest leading-none">{channelName}</span>
          <span className="text-[9px] text-gray-400 leading-none font-mono">FILTERED</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className={`text-sm font-mono font-bold leading-none ${labelColor(channelName)}`}>
            {latestValue !== null ? latestValue.toFixed(4) : '0.0000'}
          </span>
          <span className="text-[10px] text-gray-400 leading-none">m/s²</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full flex-1 min-h-0" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// FilteredChart — manages WS connection + historical data + data ingestion
// ---------------------------------------------------------------------------
export default function FilteredChart({ timeZone, timeWindowMinutes = 1, filterVersion = 0 }) {
  const timeWindowMs = timeWindowMinutes * 60 * 1000;

  // Max points to keep: based on window and effective SPS after decimation
  const getMaxPoints = (windowMin) => {
    const secs = windowMin * 60;
    if (secs <= 300) return secs * 100;       // 100 SPS
    if (secs <= 1800) return secs * 10;       // 10 SPS
    if (secs <= 21600) return secs * 1;       // 1 SPS
    return secs * 0.1;                        // 0.1 SPS
  };
  const maxPointsRef = useRef(getMaxPoints(timeWindowMinutes));

  // *** STABLE REFS — these arrays persist across renders ***
  // TimeLine is constructed with dataRefs[ch] and reads that same array object.
  const dataRefs = useRef({});
  const latestValues = useRef({});

  // Ensure arrays exist (runs once)
  if (!dataRefs.current.ENZ) {
    CHANNELS.forEach(ch => {
      dataRefs.current[ch] = [];
      latestValues.current[ch] = 0;
    });
  }

  const wsRef = useRef(null);
  const [tick, setTick] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [loading, setLoading] = useState(false);
  const reconnectDelayRef = useRef(1000);
  const lastMsgTimeRef = useRef(0);
  const isPausedRef = useRef(false);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => { isPausedRef.current = isPaused; }, [isPaused]);

  // Update maxPoints when window changes
  useEffect(() => {
    maxPointsRef.current = getMaxPoints(timeWindowMinutes);
  }, [timeWindowMinutes]);

  // -----------------------------------------------------------------------
  // Fetch historical data from DB when window or filter changes
  // -----------------------------------------------------------------------
  useEffect(() => {
    const seconds = timeWindowMinutes * 60;
    const protocol = window.location.protocol;
    const host = window.location.host;

    setLoading(true);
    fetch(`${protocol}//${host}/api/analysis/window?seconds=${seconds}`)
      .then(r => r.json())
      .then(data => {
        if (!data.timestamps || data.timestamps.length === 0) {
          // Clear existing data
          CHANNELS.forEach(ch => {
            dataRefs.current[ch].length = 0;
          });
          setLoading(false);
          setTick(t => t + 1);
          return;
        }

        CHANNELS.forEach(ch => {
          const samples = data.samples[ch] || [];
          // IMPORTANT: mutate the existing array, don't replace it.
          // TimeLine holds a reference to this exact array object.
          const arr = dataRefs.current[ch];
          arr.length = 0;  // clear in-place
          for (let i = 0; i < samples.length; i++) {
            arr.push({
              time: data.timestamps[i] * 1000,
              value: samples[i],
            });
          }
          if (samples.length > 0) {
            latestValues.current[ch] = samples[samples.length - 1];
          }
        });
        setLoading(false);
        setTick(t => t + 1);
      })
      .catch(err => {
        console.error('Failed to load analysis window:', err);
        setLoading(false);
      });
  }, [timeWindowMinutes, filterVersion]);

  // -----------------------------------------------------------------------
  // WebSocket connection to /ws/analysis — appends live filtered samples
  // -----------------------------------------------------------------------
  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }
    setConnectionStatus('connecting');

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/analysis`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      reconnectDelayRef.current = 1000;
    };

    ws.onmessage = (event) => {
      lastMsgTimeRef.current = Date.now();
      setConnectionStatus('connected');

      const msg = JSON.parse(event.data);
      const { t_start, sps, samples } = msg;

      CHANNELS.forEach(ch => {
        const arr = dataRefs.current[ch];
        const chSamples = samples[ch] || [];
        for (let i = 0; i < chSamples.length; i++) {
          arr.push({
            time: (t_start + i / sps) * 1000,
            value: chSamples[i],
          });
        }

        if (chSamples.length > 0) {
          latestValues.current[ch] = chSamples[chSamples.length - 1];
        }

        // Trim to maxPoints — remove from the front
        const max = maxPointsRef.current;
        if (arr.length > max) {
          arr.splice(0, arr.length - max);
        }
      });
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      const delay = Math.min(reconnectDelayRef.current, 30000);
      reconnectDelayRef.current = delay * 2;
      setTimeout(connect, delay);
    };

    ws.onerror = () => { ws.close(); };
  }, []);

  useEffect(() => {
    connect();

    // UI render tick (250 ms) — triggers chart.recompute()
    const uiInterval = setInterval(() => {
      if (!isPausedRef.current) setTick(t => t + 1);
    }, 250);

    // Heartbeat: detect silence
    const heartbeatInterval = setInterval(() => {
      if (lastMsgTimeRef.current > 0 && Date.now() - lastMsgTimeRef.current > 5000) {
        setConnectionStatus('no_data');
      }
    }, 3000);

    return () => {
      clearInterval(uiInterval);
      clearInterval(heartbeatInterval);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  // -----------------------------------------------------------------------
  // Status badge
  // -----------------------------------------------------------------------
  const statusBadge = () => {
    if (loading) {
      return (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 px-3 py-1 rounded border text-[10px] font-bold shadow-sm bg-white border-blue-200 text-blue-600">
          Loading historical data…
        </div>
      );
    }
    if (connectionStatus === 'connected') return null;
    const cfg = {
      connecting: { bg: 'bg-white border-yellow-200 text-yellow-600', label: 'Connecting…' },
      no_data: { bg: 'bg-white border-orange-200 text-orange-600', label: 'No Data' },
      disconnected: { bg: 'bg-white border-red-200 text-red-600', label: 'Disconnected — retrying…' },
    }[connectionStatus];
    if (!cfg) return null;
    return (
      <div className={`absolute top-2 left-1/2 -translate-x-1/2 z-10 px-3 py-1 rounded border text-[10px] font-bold shadow-sm transition-colors ${cfg.bg}`}>
        {cfg.label}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="relative flex-1 min-h-0 flex flex-col pr-1 overflow-y-auto">
        {statusBadge()}
        {CHANNELS.map(ch => (
          <AnalysisChannelPlot
            key={ch}
            channelName={ch}
            timeZone={timeZone}
            dataRef={dataRefs}  // Pass the stable parent ref — child accesses .current[ch]
            latestValue={latestValues.current[ch] || 0}
            tick={tick}
            timeWindowMs={timeWindowMs}
          />
        ))}
      </div>

      {/* Pause control */}
      <div className="flex-shrink-0 mt-2 flex items-center gap-2">
        <button
          onClick={() => setIsPaused(!isPaused)}
          className="flex items-center space-x-1.5 bg-primary hover:bg-opacity-90 text-white rounded font-bold transition-colors shadow-sm px-2.5 py-1 text-[10px]"
        >
          {isPaused ? (
            <>
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" /></svg>
              <span>RESUME</span>
            </>
          ) : (
            <>
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
              <span>PAUSE</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

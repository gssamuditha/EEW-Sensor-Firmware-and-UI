import { useEffect, useRef, useState, useCallback } from 'react';
import { useTheme } from '../ThemeContext';
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
 * Two modes driven by the `isLive` prop:
 *   1. Historical: fetches data for [startEpoch, endEpoch] from the DB,
 *      displayed with zero-phase filtering + min-max envelope downsampling.
 *   2. Live (isLive=true AND endEpoch ≈ now): loads historical data for the
 *      window, then appends real-time filtered samples from the WebSocket.
 *
 * Uses stable refs so TimeLine sees data mutations correctly.
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
  const { theme } = useTheme();
  const themeRef = useRef(theme);

  useEffect(() => { themeRef.current = theme; }, [theme]);

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
        {
          'draw:after': (chart) => {
            chart.ctx.strokeStyle = themeRef.current === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';
          }
        },
        timeAxisPlugin((x) => {
          try {
            return new Intl.DateTimeFormat('en-US', {
              timeZone, hour12: false,
              hour: 'numeric', minute: '2-digit', second: '2-digit'
            }).format(new Date(x));
          } catch { return ''; }
        }),
        valueAxisPlugin((v) => {
          const abs = Math.abs(v);
          if (abs === 0) return '0';
          if (abs >= 0.001) return v.toFixed(4);
          return v.toExponential(2);
        }),
        pointerCrosshairPlugin(),
        highlightNearestPointPlugin(),
        analysisCursorSync.plugin(),
      ],
    });
    chart.foregroundColour = themeRef.current === 'dark' ? '#cbd5e1' : '#374151';
    chart.backgroundColour = themeRef.current === 'dark' ? '#1e293b' : '#ffffff';
    chartRef.current = chart;

    return () => {
      analysisCursorSync.unregister(chart);
      if (containerRef.current) containerRef.current.innerHTML = '';
    };
  }, [timeZone, channelName]); // Note: NOT timeWindowMs — we update it dynamically below

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.foregroundColour = theme === 'dark' ? '#cbd5e1' : '#374151';
      chartRef.current.backgroundColour = theme === 'dark' ? '#1e293b' : '#ffffff';
    }
  }, [theme]);

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
    <div className="flex flex-col flex-1 min-h-[100px] mb-[2px] bg-white dark:bg-slate-800 shadow-sm p-1 rounded">
      <div className="flex items-center justify-between mb-0 px-1">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-gray-500 dark:text-slate-300 text-[10px] tracking-widest leading-none">{channelName}</span>
          <span className="text-[9px] text-gray-400 dark:text-slate-400 leading-none font-mono">FILTERED · m/s²</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <span className={`text-sm font-mono font-bold leading-none ${labelColor(channelName)}`}>
            {latestValue !== null && latestValue !== 0
              ? (Math.abs(latestValue) >= 0.001 ? latestValue.toFixed(4) : latestValue.toExponential(3))
              : '0.000'}
          </span>
          <span className="text-[10px] text-gray-400 dark:text-slate-400 leading-none">m/s²</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full flex-1 min-h-0" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// FilteredChart — manages data fetching, WS connection, data ingestion
// ---------------------------------------------------------------------------
export default function FilteredChart({ timeZone, startEpoch, endEpoch, isLive = false, filterVersion = 0 }) {
  const timeWindowMs = (endEpoch - startEpoch) * 1000;

  // Max points to keep in live mode: based on window.
  // The WS always sends at 100 SPS regardless of the window.
  // We must set the max capacity to (window at 100 SPS) + (historical downsampled points)
  // to prevent the array from prematurely trimming the historical data off the left side.
  const getMaxPoints = (windowSecs) => {
    return (windowSecs * 100) + 5000;
  };
  const maxPointsRef = useRef(getMaxPoints(endEpoch - startEpoch));

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

  // Buffer to catch WS data arriving while historical fetch is running
  const isFetchingRef = useRef(false);
  const wsBufferRef = useRef({ ENZ: [], ENN: [], ENE: [] });

  useEffect(() => { isPausedRef.current = isPaused; }, [isPaused]);

  // Update maxPoints when window changes
  useEffect(() => {
    maxPointsRef.current = getMaxPoints(endEpoch - startEpoch);
  }, [startEpoch, endEpoch]);

  // -----------------------------------------------------------------------
  // Fetch historical data from DB when time range or filter changes
  // -----------------------------------------------------------------------
  useEffect(() => {
    const protocol = window.location.protocol;
    const host = window.location.host;
    const controller = new AbortController();

    setLoading(true);
    isFetchingRef.current = true;
    
    // Clear the WS buffer at the start of a new fetch
    CHANNELS.forEach(ch => { wsBufferRef.current[ch].length = 0; });

    fetch(`${protocol}//${host}/api/analysis/window?start=${startEpoch}&end=${endEpoch}`, {
      signal: controller.signal
    })
      .then(r => r.json())
      .then(data => {
        if (!data.timestamps || data.timestamps.length === 0) {
          // Clear existing data
          CHANNELS.forEach(ch => {
            dataRefs.current[ch].length = 0;
            wsBufferRef.current[ch].length = 0;
          });
          setLoading(false);
          isFetchingRef.current = false;
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

          // Drain the WS buffer that accumulated during the fetch
          const buf = wsBufferRef.current[ch];
          for (let i = 0; i < buf.length; i++) {
            const pt = buf[i];
            // Only append points strictly newer than our last historical point
            if (arr.length === 0 || pt.time > arr[arr.length - 1].time) {
              arr.push(pt);
            }
          }
          buf.length = 0; // Clear buffer

          if (arr.length > 0) {
            latestValues.current[ch] = arr[arr.length - 1].value;
          }
        });
        
        isFetchingRef.current = false;
        setLoading(false);
        setTick(t => t + 1);
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        console.error('Failed to load analysis window:', err);
        isFetchingRef.current = false;
        setLoading(false);
      });

    return () => controller.abort();
  }, [startEpoch, endEpoch, filterVersion]);

  // -----------------------------------------------------------------------
  // WebSocket connection to /ws/analysis — only in LIVE mode
  // Appends real-time filtered samples after the historical data
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
        const chSamples = samples[ch] || [];
        // If fetch is in progress, accumulate in wsBufferRef instead of main array
        const targetArr = isFetchingRef.current ? wsBufferRef.current[ch] : dataRefs.current[ch];

        for (let i = 0; i < chSamples.length; i++) {
          const t = (t_start + i / sps) * 1000;
          // Prevent overlapping backwards points
          if (targetArr.length > 0 && t <= targetArr[targetArr.length - 1].time) {
            continue;
          }
          targetArr.push({
            time: t,
            value: chSamples[i],
          });
        }

        if (!isFetchingRef.current) {
          if (chSamples.length > 0) {
            latestValues.current[ch] = chSamples[chSamples.length - 1];
          }
          // Trim to maxPoints — remove from the front
          const max = maxPointsRef.current;
          if (targetArr.length > max) {
            targetArr.splice(0, targetArr.length - max);
          }
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

  // Manage WS lifecycle based on isLive
  useEffect(() => {
    if (isLive) {
      connect();
    } else {
      // Disconnect WS in historical-only mode
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnectionStatus('historical');
    }

    // UI render tick (250 ms) — triggers chart.recompute()
    const uiInterval = setInterval(() => {
      if (!isPausedRef.current) setTick(t => t + 1);
    }, 250);

    // Heartbeat: detect silence (only in live mode)
    const heartbeatInterval = setInterval(() => {
      if (isLive && lastMsgTimeRef.current > 0 && Date.now() - lastMsgTimeRef.current > 5000) {
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
  }, [connect, isLive]);

  // -----------------------------------------------------------------------
  // Status badge
  // -----------------------------------------------------------------------
  const statusBadge = () => {
    if (loading) {
      return (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 px-3 py-1 rounded border text-[10px] font-bold shadow-sm bg-white dark:bg-slate-800 border-blue-200 text-blue-600">
          Loading filtered data…
        </div>
      );
    }
    if (connectionStatus === 'connected' || connectionStatus === 'historical') return null;
    const cfg = {
      connecting: { bg: 'bg-white dark:bg-slate-800 border-yellow-200 text-yellow-600', label: 'Connecting…' },
      no_data: { bg: 'bg-white dark:bg-slate-800 border-orange-200 text-orange-600', label: 'No Data' },
      disconnected: { bg: 'bg-white dark:bg-slate-800 border-red-200 text-red-600', label: 'Disconnected — retrying…' },
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
          className="flex items-center space-x-1.5 bg-slate-500 dark:bg-slate-700 hover:bg-slate-600 dark:hover:bg-slate-600 text-white rounded-md font-bold transition-colors shadow-sm px-2 py-0.5 text-[10px]"
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

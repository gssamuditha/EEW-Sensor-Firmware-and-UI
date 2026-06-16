import { useEffect, useRef, useState, useCallback } from 'react';
import {
  TimeLine,
  timeAxisPlugin,
  valueAxisPlugin,
  pointerCrosshairPlugin,
  highlightNearestPointPlugin,
  doubleClickCopyPlugin,
} from '@crisislab/timeline';

const MAX_POINTS = 600;          // ~6 s at 100 SPS
const TIME_WINDOW_MS = 6000;     // 6-second sliding window
const HEARTBEAT_CHECK_MS = 3000; // how often to check for missing data
const NO_DATA_TIMEOUT_MS = 5000; // silence threshold before "NO DATA" overlay

// ---------------------------------------------------------------------------
// Shared cursor sync — broadcasts cursor position from one chart to all others
// ---------------------------------------------------------------------------
const cursorSync = {
  charts: [],
  register(chart) {
    this.charts.push(chart);
  },
  unregister(chart) {
    this.charts = this.charts.filter(c => c !== chart);
  },
  // Returns a plugin that draws a vertical sync line from other charts' cursor
  plugin() {
    let syncX = -1; // chart-relative X from the source chart

    return {
      _setSyncX(x) { syncX = x; },
      _clearSyncX() { syncX = -1; },
      construct: (chart) => {
        cursorSync.register(chart);
      },
      'draw:after': (chart) => {
        // Broadcast this chart's cursor to all other charts
        if (chart.helpfulInfo.cursor.overChart) {
          const myX = chart.helpfulInfo.cursor.chartX;
          cursorSync.charts.forEach(other => {
            if (other !== chart) {
              const otherPlugin = other.plugins.find(p => p && typeof p._setSyncX === 'function');
              if (otherPlugin) otherPlugin._setSyncX(myX);
            }
          });
        } else {
          // Mouse left this chart — clear sync line on all OTHER charts
          cursorSync.charts.forEach(other => {
            if (other !== chart) {
              const otherPlugin = other.plugins.find(p => p && typeof p._clearSyncX === 'function');
              if (otherPlugin) otherPlugin._clearSyncX();
            }
          });
        }

        // Draw sync line from another chart's cursor
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
// ChannelPlot — renders a single TimeLine chart per channel
// ---------------------------------------------------------------------------
function ChannelPlot({ channelName, timeZone, dataRef, latestValue, tick }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  // Build TimeLine instance once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = new TimeLine({
      container: containerRef.current,
      data: dataRef.current,
      timeWindow: TIME_WINDOW_MS,
      timeAxisLabel: '',
      valueAxisLabel: '',
      lineWidth: 1.2,
      // NOTE: Do NOT set padding here — the axis plugins add their own padding
      // in their construct() hooks. Setting base padding = 0 lets the plugins
      // control the layout entirely.
      plugins: [
        timeAxisPlugin((x) => {
          try {
            return new Intl.DateTimeFormat('en-US', {
              timeZone, hour12: false,
              hour: 'numeric', minute: '2-digit', second: '2-digit'
            }).format(new Date(x));
          } catch { return ''; }
        }),
        valueAxisPlugin((v) => v.toFixed(3)),
        // axisLabelPlugin removed: it adds ~40px of extra padding for "Time"/"m/s²"
        // labels that are redundant (channel name header already shows the unit)
        pointerCrosshairPlugin(),
        highlightNearestPointPlugin(),
        doubleClickCopyPlugin(),
        cursorSync.plugin(),
      ],
    });

    // Use neutral dark color for axes/border; the data line also uses this
    chart.foregroundColour = '#374151'; // gray-700 — readable for axes
    chart.backgroundColour = '#ffffff';

    chartRef.current = chart;

    return () => {
      // Unregister from cursor sync
      cursorSync.unregister(chart);
      // Clean up canvas and any plugin-created DOM elements (axis labels etc.)
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [timeZone, channelName]); // eslint-disable-line react-hooks/exhaustive-deps

  // Trigger recompute on tick (TimeLine reads the mutated data array directly)
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.recompute();
    }
  }, [tick]);

  const labelColor = (name) => {
    if (name.includes('Z')) return 'text-red-600';
    if (name.includes('N')) return 'text-teal-600';
    return 'text-yellow-600';
  };

  return (
    <div className="flex flex-col flex-1 min-h-[100px] mb-[2px] bg-white shadow-sm p-1 rounded">
      <div className="flex items-center justify-between mb-0 px-1">
        <span className="font-bold text-gray-500 text-[10px] tracking-widest leading-none">{channelName}</span>
        <div className="flex items-center space-x-1.5">
          <span className={`text-sm font-mono font-bold leading-none ${labelColor(channelName)}`}>
            {latestValue !== null ? latestValue.toFixed(4) : '0.0000'}
          </span>
          <span className="text-[10px] text-gray-400 leading-none">m/s²</span>
        </div>
      </div>
      {/* No overflow-hidden: axis plugins create positioned elements that must not be clipped.
          position:relative is set by TimeLine constructor on the container. */}
      <div ref={containerRef} className="w-full flex-1 min-h-0" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// LiveChart — WebSocket manager + data ingestion
// ---------------------------------------------------------------------------
export default function LiveChart({ timeZone, updateSps, onClientSps, onChannelsFound, isExpanded }) {
  const wsRef = useRef(null);
  const [channels, setChannels] = useState([]);
  const dataRefs = useRef({});          // { ch: [{time, value}, ...] }
  const latestValues = useRef({});
  const lastBatchEndTime = useRef({});  // { ch: number } — expected next t_start
  const [tick, setTick] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);

  // Connection state
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const lastMsgTimeRef = useRef(0);
  const reconnectDelayRef = useRef(1000);

  // SPS refs — stable across re-renders
  const updateSpsRef = useRef(updateSps);
  const onClientSpsRef = useRef(onClientSps);
  const onChannelsFoundRef = useRef(onChannelsFound);
  const channelsInitRef = useRef(false);
  const clientSpsCounter = useRef(0);

  useEffect(() => { isPausedRef.current = isPaused; }, [isPaused]);
  useEffect(() => { updateSpsRef.current = updateSps; }, [updateSps]);
  useEffect(() => { onClientSpsRef.current = onClientSps; }, [onClientSps]);
  useEffect(() => { onChannelsFoundRef.current = onChannelsFound; }, [onChannelsFound]);

  // ------------------------------------------------------------------
  // connect() — creates (or re-creates) the WebSocket, wires all handlers
  // ------------------------------------------------------------------
  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null; // prevent reconnect loop on intentional close
      wsRef.current.close();
    }
    setConnectionStatus('connecting');

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      reconnectDelayRef.current = 1000; // reset backoff
    };

    ws.onmessage = (event) => {
      lastMsgTimeRef.current = Date.now();
      setConnectionStatus('connected');

      const msg = JSON.parse(event.data);
      const { t_start, sps, samples } = msg;
      const channelNames = Object.keys(samples);
      const nSamples = samples[channelNames[0]].length;

      // Count samples for client-side SPS
      clientSpsCounter.current += nSamples;

      // First-time channel discovery
      if (!channelsInitRef.current && channelNames.length > 0) {
        channelsInitRef.current = true;
        setChannels(channelNames);
        if (onChannelsFoundRef.current) onChannelsFoundRef.current(channelNames);
        channelNames.forEach(ch => {
          dataRefs.current[ch] = [];
          latestValues.current[ch] = 0;
          lastBatchEndTime.current[ch] = null;
        });
      }

      if (isPausedRef.current) return;

      channelNames.forEach(ch => {
        if (!dataRefs.current[ch]) {
          dataRefs.current[ch] = [];
          latestValues.current[ch] = 0;
          lastBatchEndTime.current[ch] = null;
          setChannels(prev => {
            const updated = [...prev, ch];
            if (onChannelsFoundRef.current) onChannelsFoundRef.current(updated);
            return updated;
          });
        }

        // Expand batch: reconstruct per-sample timestamps
        // t_start is in seconds from the backend; TimeLine uses milliseconds
        const chSamples = samples[ch];
        for (let i = 0; i < chSamples.length; i++) {
          dataRefs.current[ch].push({
            time: (t_start + i / sps) * 1000,
            value: chSamples[i],
          });
        }

        latestValues.current[ch] = chSamples[chSamples.length - 1];
        lastBatchEndTime.current[ch] = t_start + nSamples / sps;

        // Trim to MAX_POINTS
        const arr = dataRefs.current[ch];
        if (arr.length > MAX_POINTS) {
          arr.splice(0, arr.length - MAX_POINTS);
        }
      });
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      // Exponential backoff reconnect (max 30 s)
      const delay = Math.min(reconnectDelayRef.current, 30000);
      reconnectDelayRef.current = delay * 2;
      console.log(`WS closed. Reconnecting in ${delay} ms…`);
      setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close(); // triggers onclose → reconnect
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------
  // Mount effect: connect + set up intervals
  // ------------------------------------------------------------------
  useEffect(() => {
    connect();

    // Client-side SPS report (sample count ÷ 1 s)
    const spsInterval = setInterval(() => {
      if (onClientSpsRef.current) onClientSpsRef.current(clientSpsCounter.current);
      if (updateSpsRef.current)   updateSpsRef.current(clientSpsCounter.current);
      clientSpsCounter.current = 0;
    }, 1000);

    // UI render tick (200 ms) — triggers chart.recompute() via tick state
    const uiInterval = setInterval(() => {
      if (!isPausedRef.current) setTick(t => t + 1);
    }, 200);

    // Heartbeat: detect silence
    const heartbeatInterval = setInterval(() => {
      if (lastMsgTimeRef.current > 0) {
        const silence = Date.now() - lastMsgTimeRef.current;
        if (silence > NO_DATA_TIMEOUT_MS) setConnectionStatus('no_data');
      }
    }, HEARTBEAT_CHECK_MS);

    return () => {
      clearInterval(spsInterval);
      clearInterval(uiInterval);
      clearInterval(heartbeatInterval);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);

  // ------------------------------------------------------------------
  // Pause / Resume
  // ------------------------------------------------------------------
  const togglePause = () => {
    setIsPaused(!isPaused);
  };

  // ------------------------------------------------------------------
  // Status overlay badge
  // ------------------------------------------------------------------
  const statusBadge = () => {
    if (connectionStatus === 'connected') return null;
    const cfg = {
      connecting:   { bg: 'bg-yellow-100 border-yellow-300 text-yellow-800', label: 'Connecting…' },
      no_data:      { bg: 'bg-orange-100 border-orange-300 text-orange-800', label: '⚠ No Data' },
      disconnected: { bg: 'bg-red-100   border-red-300   text-red-800',      label: '✕ Disconnected — retrying…' },
    }[connectionStatus];
    if (!cfg) return null;
    return (
      <div className={`absolute top-2 left-1/2 -translate-x-1/2 z-10 px-3 py-1 rounded-full border text-[10px] font-bold shadow-sm ${cfg.bg}`}>
        {cfg.label}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Charts area */}
      <div className="relative flex-1 min-h-0 flex flex-col pr-1 overflow-y-auto">
        {statusBadge()}
        {channels.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">Waiting for data…</div>
        ) : (
          channels.map(ch => (
            <ChannelPlot
              key={ch}
              channelName={ch}
              timeZone={timeZone}
              dataRef={{ current: dataRefs.current[ch] }}
              latestValue={latestValues.current[ch]}
              tick={tick}
            />
          ))
        )}
      </div>

      {/* Controls */}
      <div className="flex-shrink-0 mt-2 flex items-center gap-2">
        <button
          onClick={togglePause}
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

        {!isExpanded && (
          <button
            onClick={() => window.open('/expanded', '_blank')}
            className="flex items-center space-x-1.5 bg-primary hover:bg-opacity-90 text-white rounded font-bold transition-colors shadow-sm px-2.5 py-1 text-[10px]"
          >
            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
            <span>VIEW EXPANDED</span>
          </button>
        )}
      </div>
    </div>
  );
}

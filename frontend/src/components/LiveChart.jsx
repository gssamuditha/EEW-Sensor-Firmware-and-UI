import { useEffect, useRef, useState, useCallback } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

const sync = uPlot.sync("eew");
const MAX_POINTS = 600;          // ~6 s at 100 SPS
const GAP_THRESHOLD_FACTOR = 1.5; // gap > 1.5 × expected_batch_duration → flagged
const HEARTBEAT_CHECK_MS = 3000;  // how often to check for missing data
const NO_DATA_TIMEOUT_MS = 5000;  // silence threshold before "NO DATA" overlay

// ---------------------------------------------------------------------------
// ChannelPlot — renders a single uPlot trace with gap-annotation draw hook
// ---------------------------------------------------------------------------
function ChannelPlot({ channelName, timeZone, dataRef, gapsRef, latestValue, tick }) {
  const containerRef = useRef(null);
  const uPlotRef = useRef(null);

  // Build uPlot instance once (deps: timeZone, channelName)
  useEffect(() => {
    if (!containerRef.current) return;

    const opts = {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      legend: { show: false },
      cursor: { sync: { key: sync.key } },
      hooks: {
        // Raspberry Shake–style: draw translucent red bands over gap regions
        draw: [
          (u) => {
            const gaps = gapsRef.current;
            if (!gaps || gaps.length === 0) return;

            const ctx = u.ctx;
            const { left, top, width, height } = u.bbox;

            ctx.save();
            ctx.fillStyle = 'rgba(220, 38, 38, 0.18)';

            gaps.forEach(({ t_start, t_end }) => {
              const x0 = Math.max(u.valToPos(t_start, 'x', true), left);
              const x1 = Math.min(u.valToPos(t_end,   'x', true), left + width);
              if (x1 > x0) {
                ctx.fillRect(x0, top, x1 - x0, height);
                // "GAP" label
                ctx.fillStyle = 'rgba(220, 38, 38, 0.85)';
                ctx.font = 'bold 9px monospace';
                ctx.fillText('GAP', x0 + 2, top + 12);
                ctx.fillStyle = 'rgba(220, 38, 38, 0.18)';
              }
            });

            ctx.restore();
          }
        ]
      },
      scales: {
        x: {
          time: true,
          range: (u, dataMin, dataMax) => {
            if (dataMax == null) {
              const now = Date.now() / 1000;
              return [now - 5, now];
            }
            return [dataMax - 5, dataMax];
          }
        },
        y: {
          range: (u, dataMin, dataMax) => {
            if (dataMin == null || dataMax == null) return [-1, 1];
            const diff = dataMax - dataMin;
            const pad = diff === 0 ? 0.1 : diff * 0.05;
            return [dataMin - pad, dataMax + pad];
          }
        }
      },
      series: [
        { label: 'Time' },
        {
          label: channelName,
          stroke: '#1a4162',
          width: 1.2,
          spanGaps: false,
          // Custom path builder: explicitly breaks the line at null Y values.
          // This guarantees gaps render as clean breaks regardless of uPlot version.
          paths: (u, seriesIdx, idx0, idx1) => {
            const xData = u.data[0];
            const yData = u.data[seriesIdx];
            let stroke = new Path2D();
            let drawing = false;

            for (let i = idx0; i <= idx1; i++) {
              const yVal = yData[i];
              if (yVal === null || yVal === undefined) {
                drawing = false;
                continue;
              }
              const cx = Math.round(u.valToPos(xData[i], 'x', true));
              const cy = Math.round(u.valToPos(yVal,     'y', true));
              if (!drawing) {
                stroke.moveTo(cx, cy);
                drawing = true;
              } else {
                stroke.lineTo(cx, cy);
              }
            }

            return { stroke, fill: null, clip: null };
          },
        }
      ],
      axes: [
        {
          space: 60,
          splits: (u, axisIdx, scaleMin, scaleMax) => [
            scaleMax - 5, scaleMax - 4, scaleMax - 3,
            scaleMax - 2, scaleMax - 1, scaleMax
          ],
          values: (u, splits) => splits.map(s => {
            const d = new Date(s * 1000);
            try {
              return new Intl.DateTimeFormat('en-US', {
                timeZone, hour12: false,
                hour: 'numeric', minute: '2-digit', second: '2-digit'
              }).format(d);
            } catch { return s; }
          })
        },
        {
          size: 50,
          splits: (u, axisIdx, scaleMin, scaleMax) => {
            const diff = scaleMax - scaleMin;
            if (diff === 0) return [scaleMin];
            const step = diff / 4;
            return [scaleMin, scaleMin + step, scaleMin + 2 * step, scaleMin + 3 * step, scaleMax];
          },
          values: (u, vals) => vals.map(v => v.toFixed(3))
        }
      ]
    };

    const u = new uPlot(opts, [[], []], containerRef.current);
    uPlotRef.current = u;

    const handleResize = () => {
      if (containerRef.current) {
        u.setSize({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
      }
    };
    window.addEventListener('resize', handleResize);
    setTimeout(handleResize, 50);

    return () => {
      window.removeEventListener('resize', handleResize);
      u.destroy();
    };
  }, [timeZone, channelName]); // eslint-disable-line react-hooks/exhaustive-deps

  // Redraw on tick
  useEffect(() => {
    if (uPlotRef.current && dataRef.current) {
      uPlotRef.current.setData(dataRef.current);
    }
  }, [tick]);

  const labelColor = (name) => {
    if (name.includes('Z')) return 'text-red-600';
    if (name.includes('N')) return 'text-teal-600';
    return 'text-yellow-600';
  };

  return (
    <div className="flex flex-col flex-1 min-h-[100px] mb-[2px] bg-white border border-gray-100 shadow-sm p-1 rounded">
      <div className="flex items-center justify-between mb-0 px-1">
        <span className="font-bold text-gray-500 text-[10px] tracking-widest leading-none">{channelName}</span>
        <div className="flex items-center space-x-1.5">
          <span className={`text-sm font-mono font-bold leading-none ${labelColor(channelName)}`}>
            {latestValue !== null ? latestValue.toFixed(4) : '0.0000'}
          </span>
          <span className="text-[10px] text-gray-400 leading-none">m/s²</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full flex-1 min-h-0 overflow-hidden" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// LiveChart — WebSocket manager + gap detection
// ---------------------------------------------------------------------------
export default function LiveChart({ timeZone, updateSps, onClientSps, onChannelsFound, isExpanded }) {
  const wsRef = useRef(null);
  const [channels, setChannels] = useState([]);
  const dataRefs = useRef({});          // { ch: [timestamps[], values[]] }
  const gapsRefs = useRef({});          // { ch: [{t_start, t_end}] }
  const latestValues = useRef({});
  const lastBatchEndTime = useRef({});  // { ch: number } — expected next t_start
  const [tick, setTick] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(false);

  // Connection / gap state
  const [connectionStatus, setConnectionStatus] = useState('connecting'); // 'connected'|'no_data'|'disconnected'|'connecting'
  const [gapCount, setGapCount] = useState(0);
  const lastMsgTimeRef = useRef(0);
  const reconnectDelayRef = useRef(1000); // ms, doubles on each failed attempt

  // SPS refs — stable across re-renders
  const updateSpsRef = useRef(updateSps);
  const onClientSpsRef = useRef(onClientSps);
  const onChannelsFoundRef = useRef(onChannelsFound);
  const channelsInitRef = useRef(false);
  const clientSpsCounter = useRef(0); // counts samples received per second

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
      const batchDuration = nSamples / sps;
      const gapThreshold = GAP_THRESHOLD_FACTOR * batchDuration;

      // Count samples for client-side SPS
      clientSpsCounter.current += nSamples;

      // First-time channel discovery
      if (!channelsInitRef.current && channelNames.length > 0) {
        channelsInitRef.current = true;
        setChannels(channelNames);
        if (onChannelsFoundRef.current) onChannelsFoundRef.current(channelNames);
        channelNames.forEach(ch => {
          dataRefs.current[ch] = [[], []];
          gapsRefs.current[ch] = [];
          latestValues.current[ch] = 0;
          lastBatchEndTime.current[ch] = null;
        });
      }

      if (isPausedRef.current) return;

      channelNames.forEach(ch => {
        if (!dataRefs.current[ch]) {
          dataRefs.current[ch] = [[], []];
          gapsRefs.current[ch] = [];
          latestValues.current[ch] = 0;
          lastBatchEndTime.current[ch] = null;
          setChannels(prev => {
            const updated = [...prev, ch];
            if (onChannelsFoundRef.current) onChannelsFoundRef.current(updated);
            return updated;
          });
        }

        const expectedNext = lastBatchEndTime.current[ch];

        // --- Gap detection (rsudp / Raspberry Shake approach) ---
        // Expected next t_start = previous t_start + N_samples / sps
        // If the actual t_start deviates by more than GAP_THRESHOLD, flag it
        if (expectedNext !== null && (t_start - expectedNext) > gapThreshold) {
          // Insert null sentinels so uPlot renders a clean trace break
          dataRefs.current[ch][0].push(expectedNext + 0.001);
          dataRefs.current[ch][1].push(null);
          dataRefs.current[ch][0].push(t_start - 0.001);
          dataRefs.current[ch][1].push(null);

          // Record for red overlay annotation
          gapsRefs.current[ch].push({ t_start: expectedNext, t_end: t_start });
          setGapCount(c => c + 1);
        }

        // Expand batch: reconstruct per-sample timestamps (same as ADXL354.py logic:
        //   only t_start is transmitted; individual times derived from index/sps)
        const chSamples = samples[ch];
        for (let i = 0; i < chSamples.length; i++) {
          dataRefs.current[ch][0].push(t_start + i / sps);
          dataRefs.current[ch][1].push(chSamples[i]);
        }

        latestValues.current[ch] = chSamples[chSamples.length - 1];
        lastBatchEndTime.current[ch] = t_start + nSamples / sps;

        // Trim to MAX_POINTS
        const ts = dataRefs.current[ch][0];
        const vs = dataRefs.current[ch][1];
        if (ts.length > MAX_POINTS) {
          const excess = ts.length - MAX_POINTS;
          ts.splice(0, excess);
          vs.splice(0, excess);
        }

        // Prune gap annotations that have scrolled off the visible window
        const viewStart = ts[0] ?? 0;
        gapsRefs.current[ch] = gapsRefs.current[ch].filter(g => g.t_end > viewStart);
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

    // UI render tick (200 ms)
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
              gapsRef={{ current: gapsRefs.current[ch] }}
              latestValue={latestValues.current[ch]}
              tick={tick}
            />
          ))
        )}
      </div>

      {/* Controls */}
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

        {/* Gap counter badge */}
        {gapCount > 0 && (
          <div className="flex items-center space-x-1 px-2 py-1 bg-red-50 border border-red-200 rounded text-[10px] font-bold text-red-700">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
            <span>{gapCount} GAP{gapCount !== 1 ? 'S' : ''} DETECTED</span>
          </div>
        )}

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

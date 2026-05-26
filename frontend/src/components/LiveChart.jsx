import { useEffect, useRef, useState } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

const sync = uPlot.sync("eew");
const MAX_POINTS = 500;

function ChannelPlot({ channelName, timeZone, dataRef, latestValue, tick }) {
  const containerRef = useRef(null);
  const uPlotRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const opts = {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight, // Maximize plot height
      legend: { show: false }, // Remove legend
      cursor: { sync: { key: sync.key } },
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
            // Add tiny 5% padding so peaks don't hit the exact pixel edge, 
            // but keep it tightly bound to visible data
            const diff = dataMax - dataMin;
            const pad = diff === 0 ? 0.1 : diff * 0.05;
            return [dataMin - pad, dataMax + pad];
          }
        }
      },
      series: [
        { label: "Time" },
        { label: channelName, stroke: "#1a4162", width: 1.2 }
      ],
      axes: [
        {
          space: 60,
          splits: (u, axisIdx, scaleMin, scaleMax) => {
             // Fixed positions relative to the max visible time (right edge)
             return [
                scaleMax - 5,
                scaleMax - 4,
                scaleMax - 3,
                scaleMax - 2,
                scaleMax - 1,
                scaleMax
             ];
          },
          values: (u, splits) => splits.map(s => {
             const d = new Date(s * 1000);
             try {
                 return new Intl.DateTimeFormat('en-US', {
                   timeZone: timeZone,
                   hour12: false,
                   hour: 'numeric', minute: '2-digit', second: '2-digit'
                 }).format(d);
             } catch(e) {
                 return s;
             }
          })
        },
        {
          size: 50,
          splits: (u, axisIdx, scaleMin, scaleMax) => {
            const diff = scaleMax - scaleMin;
            if (diff === 0) return [scaleMin];
            const step = diff / 4;
            return [
              scaleMin,
              scaleMin + step,
              scaleMin + 2 * step,
              scaleMin + 3 * step,
              scaleMax
            ];
          },
          values: (u, vals) => vals.map(v => v.toFixed(3))
        }
      ]
    };

    const u = new uPlot(opts, [[], []], containerRef.current);
    uPlotRef.current = u;

    const handleResize = () => {
      if (containerRef.current) {
        u.setSize({ 
          width: containerRef.current.clientWidth, 
          height: containerRef.current.clientHeight 
        });
      }
    };
    window.addEventListener('resize', handleResize);
    // Initial size fix in case of flex layout taking a moment
    setTimeout(handleResize, 50);

    return () => {
      window.removeEventListener('resize', handleResize);
      u.destroy();
    };
  }, [timeZone, channelName]);

  useEffect(() => {
    if (uPlotRef.current && dataRef.current) {
      uPlotRef.current.setData(dataRef.current);
    }
  }, [tick]);

  const getColor = (name) => {
    if (name.includes('Z')) return 'text-red-600';
    if (name.includes('N')) return 'text-teal-600';
    if (name.includes('E')) return 'text-yellow-600';
    return 'text-blue-600';
  };

  return (
    <div className="flex flex-col flex-1 min-h-[100px] mb-[2px] bg-white border border-gray-100 shadow-sm p-1 rounded">
      <div className="flex items-center justify-between mb-0 px-1">
        <span className="font-bold text-gray-500 text-[10px] tracking-widest leading-none">{channelName}</span>
        <div className="flex items-center space-x-1.5">
          <span className={`text-sm font-mono font-bold leading-none ${getColor(channelName)}`}>
            {latestValue !== null ? latestValue.toFixed(4) : "0.0000"}
          </span>
          <span className="text-[10px] text-gray-400 leading-none">m/s²</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full flex-1 min-h-0 overflow-hidden"></div>
    </div>
  );
}

export default function LiveChart({ timeZone, updateSps, onChannelsFound, isExpanded }) {
  const wsRef = useRef(null);
  const [channels, setChannels] = useState([]);
  const dataRefs = useRef({}); 
  const latestValues = useRef({});
  const [tick, setTick] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const isPausedRef = useRef(isPaused);
  
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsRef.current = new WebSocket(`${wsProtocol}//${window.location.host}/ws/stream`);
    
    let spsCounter = 0;
    const spsInterval = setInterval(() => {
      if (updateSps) updateSps(spsCounter);
      spsCounter = 0;
    }, 1000);
    
    const uiInterval = setInterval(() => {
      if (!isPausedRef.current) {
        setTick(t => t + 1);
      }
    }, 200);
    
    wsRef.current.onmessage = (event) => {
      // Background buffering: We no longer return early when paused.
      // Data continues to accumulate in dataRefs.
      spsCounter++;
      const data = JSON.parse(event.data);
      const { t, ...chData } = data;
      
      const newChannels = Object.keys(chData);
      
      if (channels.length === 0 && newChannels.length > 0) {
        setChannels(newChannels);
        if (onChannelsFound) onChannelsFound(newChannels);
        newChannels.forEach(ch => {
          dataRefs.current[ch] = [[], []];
          latestValues.current[ch] = 0;
        });
      }
      
      newChannels.forEach(ch => {
        if (!dataRefs.current[ch]) {
            dataRefs.current[ch] = [[], []];
            setChannels(prev => {
              const updated = [...prev, ch];
              if (onChannelsFound) onChannelsFound(updated);
              return updated;
            });
        }
        dataRefs.current[ch][0].push(t);
        dataRefs.current[ch][1].push(chData[ch]);
        latestValues.current[ch] = chData[ch];
        
        if (dataRefs.current[ch][0].length > MAX_POINTS) {
          dataRefs.current[ch][0].shift();
          dataRefs.current[ch][1].shift();
        }
      });
    };

    return () => {
      clearInterval(spsInterval);
      clearInterval(uiInterval);
      if (wsRef.current) wsRef.current.close();
    };
  }, [updateSps, channels.length, onChannelsFound]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-1 min-h-0 flex flex-col pr-1 overflow-y-auto">
        {channels.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm text-gray-400">Waiting for data...</div>
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
      
      <div className="flex-shrink-0 mt-2 flex items-center gap-2">
        <button 
          onClick={() => setIsPaused(!isPaused)}
          className={`flex items-center space-x-1.5 bg-primary hover:bg-opacity-90 text-white rounded font-bold transition-colors shadow-sm px-2.5 py-1 text-[10px]`}
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

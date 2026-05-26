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
      height: 100,
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
        }
      },
      series: [
        { label: "Time" },
        { label: channelName, stroke: "#0ea5e9", width: 1.5 }
      ],
      axes: [
        {
          space: 60,
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
          values: (u, vals) => vals.map(v => v.toFixed(3))
        }
      ]
    };

    const u = new uPlot(opts, [[], []], containerRef.current);
    uPlotRef.current = u;

    const handleResize = () => {
      if (containerRef.current) {
        u.setSize({ width: containerRef.current.clientWidth, height: 100 });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      u.destroy();
    };
  }, [timeZone, channelName]);

  useEffect(() => {
    if (uPlotRef.current && dataRef.current) {
      uPlotRef.current.setData(dataRef.current);
    }
  }, [tick]); // Update uPlot on every tick

  const getColor = (name) => {
    if (name.includes('Z')) return 'text-red-600';
    if (name.includes('N')) return 'text-teal-600';
    if (name.includes('E')) return 'text-yellow-600';
    return 'text-blue-600';
  };

  return (
    <div className="flex flex-col mb-3 bg-white border border-gray-100 shadow-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-gray-500 text-xs tracking-widest">{channelName}</span>
        <div className="flex items-center space-x-2">
          <span className={`text-lg font-mono font-bold ${getColor(channelName)}`}>
            {latestValue !== null ? latestValue.toFixed(4) : "0.0000"}
          </span>
          <span className="text-xs text-gray-400">m/s²</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full overflow-hidden"></div>
    </div>
  );
}

export default function LiveChart({ timeZone, updateSps, onChannelsFound }) {
  const wsRef = useRef(null);
  const [channels, setChannels] = useState([]);
  const dataRefs = useRef({}); 
  const latestValues = useRef({});
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsRef.current = new WebSocket(`${wsProtocol}//${window.location.host}/ws/stream`);
    
    let spsCounter = 0;
    const spsInterval = setInterval(() => {
      if (updateSps) updateSps(spsCounter);
      spsCounter = 0;
    }, 1000);
    
    const uiInterval = setInterval(() => {
      setTick(t => t + 1);
    }, 200);
    
    wsRef.current.onmessage = (event) => {
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
    <div className="flex flex-col h-full overflow-y-auto pr-2 custom-scrollbar">
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
  );
}

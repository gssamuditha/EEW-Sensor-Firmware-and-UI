import { useEffect, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

const sync = uPlot.sync("eew");

export default function LiveChart({ timeZone, updateReadouts, updateSps }) {
  const containerEne = useRef(null);
  const containerEnn = useRef(null);
  const containerEnz = useRef(null);
  
  const uEne = useRef(null);
  const uEnn = useRef(null);
  const uEnz = useRef(null);
  
  const wsRef = useRef(null);
  
  const dataEne = useRef([[], []]); // Y
  const dataEnn = useRef([[], []]); // X
  const dataEnz = useRef([[], []]); // Z
  
  const MAX_POINTS = 500;

  useEffect(() => {
    if (!containerEne.current || !containerEnn.current || !containerEnz.current) return;

    const makeOpts = (container, label) => ({
      width: container.clientWidth,
      height: 180,
      cursor: {
        sync: { key: sync.key }
      },
      series: [
        { label: "Time" },
        { label: label, stroke: "#000000", width: 1 }
      ],
      axes: [
        {
          space: 80,
          values: (u, splits) => splits.map(s => {
             const d = new Date(s * 1000);
             try {
                 return new Intl.DateTimeFormat('en-US', {
                   timeZone: timeZone,
                   hour12: true,
                   hour: 'numeric', minute: '2-digit', second: '2-digit'
                 }).format(d);
             } catch(e) {
                 return s;
             }
          })
        },
        {
          size: 70,
          values: (u, vals) => vals.map(v => v.toFixed(4))
        }
      ]
    });

    // The screenshot shows ENE at the top, ENN in middle, ENZ at bottom
    const u_ene = new uPlot(makeOpts(containerEne.current, "ENE"), [[], []], containerEne.current);
    const u_enn = new uPlot(makeOpts(containerEnn.current, "ENN"), [[], []], containerEnn.current);
    const u_enz = new uPlot(makeOpts(containerEnz.current, "ENZ"), [[], []], containerEnz.current);

    uEne.current = u_ene;
    uEnn.current = u_enn;
    uEnz.current = u_enz;

    const handleResize = () => {
      [
        { u: u_ene, c: containerEne.current },
        { u: u_enn, c: containerEnn.current },
        { u: u_enz, c: containerEnz.current }
      ].forEach(({u, c}) => {
        if (c) u.setSize({ width: c.clientWidth, height: 180 });
      });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      u_ene.destroy();
      u_enn.destroy();
      u_enz.destroy();
    };
  }, [timeZone]);

  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsRef.current = new WebSocket(`${wsProtocol}//${window.location.host}/ws/stream`);
    let messageCount = 0;
    
    let spsCounter = 0;
    const spsInterval = setInterval(() => {
      if (updateSps) updateSps(spsCounter);
      spsCounter = 0;
    }, 1000);
    
    wsRef.current.onmessage = (event) => {
      spsCounter++;
      const data = JSON.parse(event.data);
      const { t, z, x, y } = data; // z=ENZ, x=ENN, y=ENE
      
      dataEne.current[0].push(t);
      dataEne.current[1].push(y);
      
      dataEnn.current[0].push(t);
      dataEnn.current[1].push(x);
      
      dataEnz.current[0].push(t);
      dataEnz.current[1].push(z);

      if (dataEne.current[0].length > MAX_POINTS) {
        dataEne.current[0].shift();
        dataEne.current[1].shift();
        
        dataEnn.current[0].shift();
        dataEnn.current[1].shift();
        
        dataEnz.current[0].shift();
        dataEnz.current[1].shift();
      }

      messageCount++;
      if (updateReadouts && messageCount % 10 === 0) {
        updateReadouts(z, x, y);
      }
      
      if (messageCount % 10 === 0) {
        if (uEne.current && uEnn.current && uEnz.current) {
          uEne.current.setData(dataEne.current);
          uEnn.current.setData(dataEnn.current);
          uEnz.current.setData(dataEnz.current);
        }
      }
    };

    return () => {
      clearInterval(spsInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [updateReadouts, updateSps]);

  return (
    <div className="flex flex-col space-y-4">
      <div className="flex items-stretch bg-white border border-gray-300 shadow-sm">
        <div className="w-12 bg-gray-50 flex items-center justify-center border-r border-gray-300">
          <span className="transform -rotate-90 text-xs font-bold text-black tracking-widest">ENE</span>
        </div>
        <div ref={containerEne} className="flex-1 w-full overflow-hidden"></div>
      </div>
      
      <div className="flex items-stretch bg-white border border-gray-300 shadow-sm">
        <div className="w-12 bg-gray-50 flex items-center justify-center border-r border-gray-300">
          <span className="transform -rotate-90 text-xs font-bold text-black tracking-widest">ENN</span>
        </div>
        <div ref={containerEnn} className="flex-1 w-full overflow-hidden"></div>
      </div>
      
      <div className="flex items-stretch bg-white border border-gray-300 shadow-sm">
        <div className="w-12 bg-gray-50 flex items-center justify-center border-r border-gray-300">
          <span className="transform -rotate-90 text-xs font-bold text-black tracking-widest">ENZ</span>
        </div>
        <div ref={containerEnz} className="flex-1 w-full overflow-hidden"></div>
      </div>
    </div>
  );
}

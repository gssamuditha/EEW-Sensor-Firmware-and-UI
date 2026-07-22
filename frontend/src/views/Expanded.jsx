import { useTimeZone } from '../TimeZoneContext';
import LiveChart from '../components/LiveChart';

export default function Expanded() {
  const { timeZone } = useTimeZone();
  
  return (
    <div className="flex flex-col h-screen w-screen bg-gray-50 dark:bg-slate-900 overflow-hidden p-4">
      <div className="flex-1 min-h-0 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-4 shadow-sm flex flex-col">
        <LiveChart timeZone={timeZone} isExpanded={true} />
      </div>
    </div>
  );
}

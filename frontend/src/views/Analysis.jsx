export default function Analysis() {
  return (
    <div className="p-8 h-full bg-gray-50 flex flex-col">
      <h2 className="text-2xl font-bold text-primary tracking-wide mb-8 uppercase">Analysis & Logs</h2>
      <div className="bg-white border border-gray-200 shadow-sm p-8 text-center text-gray-500 font-mono text-sm">
        <p>No historical trigger logs available yet.</p>
        <p className="mt-2 text-xs">Run processing tasks to populate this view.</p>
      </div>
    </div>
  );
}

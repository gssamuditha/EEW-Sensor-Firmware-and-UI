import Sidebar from './Sidebar';

export default function Layout({ children }) {
  return (
    <div className="fixed inset-0 flex flex-col-reverse md:flex-row bg-gray-50 dark:bg-slate-900 overflow-hidden font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col h-full overflow-y-auto min-h-0">
        {children}
      </main>
    </div>
  );
}

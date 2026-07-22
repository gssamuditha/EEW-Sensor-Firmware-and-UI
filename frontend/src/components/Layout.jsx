import Sidebar from './Sidebar';

export default function Layout({ children }) {
  return (
    <div className="flex h-screen w-full bg-gray-50 dark:bg-slate-900 overflow-hidden font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col h-full overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

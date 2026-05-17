import Sidebar from './Sidebar';

export default function Layout({ children }) {
  return (
    <div className="flex h-screen w-full bg-background overflow-hidden font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col h-full overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

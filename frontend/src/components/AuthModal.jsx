import { useState, useEffect, useRef } from 'react';
import { LockClosedIcon, EyeIcon, EyeSlashIcon, XMarkIcon } from '@heroicons/react/24/solid';

/**
 * AuthModal — Password prompt for protected EEW sensor operations.
 *
 * Props:
 *   isOpen    {bool}  — controls modal visibility
 *   onSuccess {fn}    — called with (token, ttl) after correct password
 *   onCancel  {fn}    — called when user dismisses the modal
 */
export default function AuthModal({ isOpen, onSuccess, onCancel }) {
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [shake, setShake]       = useState(false);
  const inputRef                = useRef(null);

  // Focus the input whenever the modal opens; reset state on close
  useEffect(() => {
    if (isOpen) {
      setPassword('');
      setError('');
      setLoading(false);
      setShake(false);
      setShowPw(false);
      setTimeout(() => inputRef.current?.focus(), 60);
    }
  }, [isOpen]);

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 600);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password || loading) return;

    setLoading(true);
    setError('');

    try {
      const res  = await fetch('/api/auth/verify', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ password }),
      });
      const data = await res.json();

      if (res.ok) {
        onSuccess(data.token, data.ttl);
        setPassword('');
      } else {
        setError(data.detail || 'Incorrect password');
        triggerShake();
        setPassword('');
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    } catch {
      setError('Network error — check connection');
      triggerShake();
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[70] flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className={`bg-white dark:bg-slate-800 p-6 max-w-sm w-full shadow-2xl border border-slate-100 dark:border-slate-700 rounded-xl ${shake ? 'animate-shake' : ''}`}>

        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[#1a4162]/10 dark:bg-sky-900/40 flex items-center justify-center shrink-0">
              <LockClosedIcon className="w-4 h-4 text-[#1a4162] dark:text-sky-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-200 tracking-wide leading-tight">
                Admin Authentication
              </h3>
              <p className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">
                Required for critical changes
              </p>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors p-1"
            aria-label="Cancel"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="relative mb-3">
            <input
              ref={inputRef}
              id="auth-password-input"
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter admin password"
              autoComplete="current-password"
              className="w-full bg-slate-100 dark:bg-slate-700 border-0 rounded-lg px-4 py-2.5 pr-10 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#1a4162]/30 dark:focus:ring-sky-500/40 placeholder:text-slate-400"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
              tabIndex={-1}
              aria-label={showPw ? 'Hide password' : 'Show password'}
            >
              {showPw
                ? <EyeSlashIcon className="w-4 h-4" />
                : <EyeIcon       className="w-4 h-4" />}
            </button>
          </div>

          {error && (
            <p className="text-xs font-bold text-red-600 dark:text-red-400 font-mono mb-3 flex items-center gap-1">
              <span aria-hidden="true">⚠</span> {error}
            </p>
          )}

          <div className="flex gap-3 mt-4">
            <button
              type="button"
              onClick={onCancel}
              className="flex-1 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-bold uppercase tracking-wider py-2 rounded-lg transition-colors text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              id="auth-unlock-btn"
              disabled={loading || !password}
              className="flex-1 bg-[#1a4162] dark:bg-sky-600 hover:bg-[#1a4162]/90 dark:hover:bg-sky-700 text-white font-bold uppercase tracking-wider py-2 rounded-lg transition-colors text-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
              ) : (
                <LockClosedIcon className="w-4 h-4" />
              )}
              {loading ? 'Verifying…' : 'Unlock'}
            </button>
          </div>
        </form>

        <p className="text-[10px] text-slate-400 dark:text-slate-500 font-mono text-center mt-4">
          Default: <span className="font-bold">cl123</span> — change it in Settings → System → Admin Password
        </p>
      </div>
    </div>
  );
}

import { useState, useCallback, useRef } from 'react';

/**
 * useAuth — Manages session token state for protected EEW sensor operations.
 *
 * The token is held in React state (memory) only and is never written to
 * localStorage or sessionStorage. It is cleared automatically when the browser
 * tab is closed or the page is refreshed.
 *
 * Usage:
 *   const { requireAuth, showAuthModal, handleAuthSuccess, handleAuthCancel } = useAuth();
 *
 *   // Wrap any protected action:
 *   const handleSave = () => requireAuth(async (token) => {
 *     await fetch('/api/settings', {
 *       headers: { 'X-Auth-Token': token },
 *       ...
 *     });
 *   });
 */
export function useAuth() {
  // Session token and its server-side expiry timestamp (Unix seconds)
  const [token,       setToken]       = useState(null);
  const [tokenExpiry, setTokenExpiry] = useState(0);

  // Whether the auth modal is currently visible
  const [showAuthModal, setShowAuthModal] = useState(false);

  // Pending action stored in a ref so stale closures don't capture old state
  const pendingActionRef = useRef(null);

  /** Returns true when a valid, non-expired token is held in memory. */
  const isAuthenticated = useCallback(() => {
    return token !== null && Math.floor(Date.now() / 1000) < tokenExpiry;
  }, [token, tokenExpiry]);

  /**
   * Wraps a protected async action.
   * - If a valid token is already held: calls action(token) immediately.
   * - Otherwise: stores the action and shows the password modal; the action
   *   will be fired once the user authenticates successfully.
   *
   * @param {(token: string) => void} action  Async function that receives the auth token.
   */
  const requireAuth = useCallback((action) => {
    if (token && Math.floor(Date.now() / 1000) < tokenExpiry) {
      // Token still valid — fire the action right away
      action(token);
    } else {
      // No valid token — show the auth modal and queue the action
      pendingActionRef.current = action;
      setShowAuthModal(true);
    }
  }, [token, tokenExpiry]);

  /**
   * Called by AuthModal on successful authentication.
   * Stores the new token, hides the modal, and fires the pending action.
   *
   * @param {string} newToken  HMAC session token from the server.
   * @param {number} ttl       Token lifetime in seconds (from the server).
   */
  const handleAuthSuccess = useCallback((newToken, ttl) => {
    setToken(newToken);
    // Subtract a 30-second buffer so we prompt for re-auth before the server
    // rejects the token mid-request.
    setTokenExpiry(Math.floor(Date.now() / 1000) + ttl - 30);
    setShowAuthModal(false);
    if (pendingActionRef.current) {
      pendingActionRef.current(newToken);
      pendingActionRef.current = null;
    }
  }, []);

  /** Called by AuthModal when the user cancels. Discards the pending action. */
  const handleAuthCancel = useCallback(() => {
    setShowAuthModal(false);
    pendingActionRef.current = null;
  }, []);

  return {
    requireAuth,
    showAuthModal,
    handleAuthSuccess,
    handleAuthCancel,
    token,
    isAuthenticated,
  };
}

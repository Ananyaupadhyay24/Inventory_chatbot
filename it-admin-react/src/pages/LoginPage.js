import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

const LOGO_SRC = "data:image/png;base64,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";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username, password);
    } catch {
      setError('Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.root}>
      {/* Background decoration */}
      <div style={styles.bgDecor1} />
      <div style={styles.bgDecor2} />
      <div style={styles.bgPattern} aria-hidden="true" />

      <div style={styles.card}>
        {/* Orange top bar */}
        <div style={styles.topBar} />

        <div style={styles.cardBody}>
          {/* Logo */}
          <div style={styles.logoWrap}>
            <img src={LOGO_SRC} alt="Netsmartz" style={styles.logoImg} />
          </div>

          <div style={styles.divider} />

          <h1 style={styles.title}>IT Inventory System</h1>
          <p style={styles.subtitle}>Sign in to manage and monitor your assets</p>

          <form onSubmit={handleSubmit} style={styles.form}>
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Username</label>
              <div style={styles.inputWrap}>
                <svg style={styles.inputIcon} width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="5" r="3" stroke="#8b92a5" strokeWidth="1.2"/>
                  <path d="M1 13s1-4 6-4 6 4 6 4" stroke="#8b92a5" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
                <input
                  style={styles.input}
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder="Enter username"
                  required
                  autoComplete="username"
                />
              </div>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Password</label>
              <div style={styles.inputWrap}>
                <svg style={styles.inputIcon} width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <rect x="2" y="6" width="10" height="7" rx="1.5" stroke="#8b92a5" strokeWidth="1.2"/>
                  <path d="M4 6V4.5a3 3 0 016 0V6" stroke="#8b92a5" strokeWidth="1.2"/>
                </svg>
                <input
                  style={styles.input}
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  autoComplete="current-password"
                />
              </div>
            </div>

            {error && (
              <div style={styles.error}>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <circle cx="6.5" cy="6.5" r="5.5" stroke="#dc2626" strokeWidth="1.1"/>
                  <path d="M6.5 3.5v3.5M6.5 9v.5" stroke="#dc2626" strokeWidth="1.2" strokeLinecap="round"/>
                </svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              style={{ ...styles.btn, ...(loading ? styles.btnLoading : {}) }}
              disabled={loading}
            >
              {loading ? (
                <span style={styles.spinnerWrap}>
                  <span style={styles.spinner} />
                  Signing in...
                </span>
              ) : (
                <>
                  Sign In
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </>
              )}
            </button>
          </form>

          <div style={styles.hint}>
            <div style={styles.hintLabel}>
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                <circle cx="5.5" cy="5.5" r="4.5" stroke="var(--accent-orange)" strokeWidth="1"/>
                <path d="M5.5 4v2.5M5.5 7.5v.3" stroke="var(--accent-orange)" strokeWidth="1" strokeLinecap="round"/>
              </svg>
              Default credentials
            </div>
            <div style={styles.hintCreds}>
              <code style={styles.code}>admin / admin123</code>
              <code style={styles.code}>viewer / viewer123</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: {
    minHeight: '100vh',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--bg-base)',
    position: 'relative', overflow: 'hidden',
    fontFamily: 'var(--font-body)',
  },
  bgDecor1: {
    position: 'absolute', top: -120, right: -120,
    width: 500, height: 500, borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(249,115,22,0.12) 0%, transparent 70%)',
    pointerEvents: 'none',
  },
  bgDecor2: {
    position: 'absolute', bottom: -80, left: -100,
    width: 400, height: 400, borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(249,115,22,0.07) 0%, transparent 70%)',
    pointerEvents: 'none',
  },
  bgPattern: {
    position: 'absolute', inset: 0,
    backgroundImage: `radial-gradient(circle, rgba(249,115,22,0.06) 1px, transparent 1px)`,
    backgroundSize: '28px 28px',
    pointerEvents: 'none',
  },
  card: {
    width: 420,
    background: 'var(--bg-surface)',
    borderRadius: 20,
    boxShadow: '0 20px 60px rgba(15,17,23,0.12), 0 4px 16px rgba(249,115,22,0.06)',
    overflow: 'hidden',
    position: 'relative', zIndex: 1,
    border: '1px solid var(--border)',
  },
  topBar: {
    height: 5,
    background: 'linear-gradient(90deg, #f97316 0%, #fb923c 60%, #fdba74 100%)',
  },
  cardBody: { padding: '20px 40px 20px' },
  logoWrap: { display: 'flex', justifyContent: 'center', marginBottom: 12 },
  logoImg: { height: 100, objectFit: 'contain' },
  divider: { height: 1, background: 'var(--border)', marginBottom: 14 },
  title: {
    fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700,
    color: 'var(--text-primary)', marginBottom: 4, letterSpacing: '-0.02em',
  },
  subtitle: { fontSize: 13.5, color: 'var(--text-secondary)', marginBottom: 14 },
  form: { display: 'flex', flexDirection: 'column', gap: 11 },
  fieldGroup: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: {
    fontSize: 11.5, fontWeight: 600, color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '0.07em',
  },
  inputWrap: { position: 'relative' },
  inputIcon: { position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' },
  input: {
    width: '100%', paddingLeft: 36, paddingRight: 14, paddingTop: 10, paddingBottom: 10,
    background: 'var(--bg-elevated)',
    border: '1.5px solid var(--border)',
    borderRadius: 10, color: 'var(--text-primary)',
    fontSize: 14, outline: 'none', transition: 'border-color 0.15s',
    fontFamily: 'var(--font-body)',
  },
  error: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: 'var(--accent-red-dim)', border: '1px solid rgba(220,38,38,0.2)',
    borderRadius: 8, padding: '9px 12px', color: 'var(--accent-red)', fontSize: 13,
  },
  btn: {
    background: 'linear-gradient(135deg, #f97316 0%, #ea6b0a 100%)',
    color: '#fff', border: 'none', borderRadius: 10,
    padding: '12px 20px',
    fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14.5,
    cursor: 'pointer', letterSpacing: '0.01em', marginTop: 4,
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    minHeight: 46,
    boxShadow: '0 4px 14px rgba(249,115,22,0.35)',
    transition: 'opacity 0.15s, transform 0.1s',
  },
  btnLoading: { opacity: 0.75, cursor: 'not-allowed' },
  spinnerWrap: { display: 'flex', alignItems: 'center', gap: 8 },
  spinner: {
    width: 16, height: 16,
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff', borderRadius: '50%',
    display: 'inline-block',
  },
  hint: {
    marginTop: 14, padding: '10px 14px',
    background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 10,
  },
  hintLabel: {
    display: 'flex', alignItems: 'center', gap: 5,
    fontSize: 11, color: 'var(--accent-orange)', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
  },
  hintCreds: { display: 'flex', flexDirection: 'column', gap: 4 },
  code: {
    fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-orange)',
    background: 'var(--accent-orange-dim)', padding: '3px 8px', borderRadius: 5,
    display: 'inline-block', width: 'fit-content',
  },
};

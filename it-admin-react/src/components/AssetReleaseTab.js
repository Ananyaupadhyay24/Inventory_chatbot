import React, { useState, useEffect } from 'react';
import api from '../utils/api';
import DataTable from './DataTable';
import { useAuth } from '../context/AuthContext';

const LOCATIONS = ['GGN', 'Noida', 'CHD', 'Mohali', '5th Floor', '6th Floor', '7th Floor'];

export default function AssetReleaseTab() {
  const { auth } = useAuth();
  const [identifier,    setIdentifier]    = useState('');
  const [newLocation,   setNewLocation]   = useState('GGN');
  const [preview,       setPreview]       = useState(null);
  const [stock,         setStock]         = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [releasing,     setReleasing]     = useState(false);
  const [successMsg,    setSuccessMsg]    = useState('');
  const [stockLoading,  setStockLoading]  = useState(true);

  useEffect(() => {
    setStockLoading(true);
    api.get('/assets/stock')
      .then(r => setStock(r.data))
      .catch(() => {})
      .finally(() => setStockLoading(false));
  }, [successMsg]);

  const handlePreview = async (e) => {
    e.preventDefault();
    if (!identifier.trim()) return;
    setLoading(true); setPreview(null); setSuccessMsg('');
    try {
      const res = await api.post('/assets/release/preview', { identifier: identifier.trim() });
      setPreview(res.data);
    } catch (err) {
      alert(err.response?.data?.detail || 'Preview failed');
    } finally { setLoading(false); }
  };

  const handleConfirm = async () => {
    setReleasing(true);
    try {
      const res = await api.post('/assets/release/confirm', {
        identifier: identifier.trim(), new_location: newLocation,
      });
      setSuccessMsg(res.data.message);
      setPreview(null); setIdentifier('');
    } catch (err) {
      alert(err.response?.data?.detail || 'Release failed');
    } finally { setReleasing(false); }
  };

  const isAdmin = auth?.role === 'admin';

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <h2 style={styles.title}>Asset Release</h2>
        <p style={styles.subtitle}>Free all devices assigned to a departing employee and move them to IT Stock</p>
      </div>

      <div style={styles.body}>
        {/* Release Form Card */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardIconWrap}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="6" cy="5" r="3" stroke="var(--accent-orange)" strokeWidth="1.3"/>
                <path d="M1 14s1-4 5-4M10 9l4 4M14 9l-4 4" stroke="var(--accent-orange)" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <div style={styles.cardTitle}>Employee Exit — Release Devices</div>
              <div style={styles.cardSub}>Preview and confirm device reassignment to IT Stock</div>
            </div>
          </div>

          <form onSubmit={handlePreview} style={styles.form}>
            <div style={styles.formRow}>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Employee Name or Code</label>
                <input
                  style={styles.input}
                  value={identifier}
                  onChange={e => setIdentifier(e.target.value)}
                  placeholder="e.g. Anjali Garg or NTZ2076"
                  required
                />
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Move to Stock Location</label>
                <select style={styles.select} value={newLocation} onChange={e => setNewLocation(e.target.value)}>
                  {LOCATIONS.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
            </div>
            <button type="submit" style={styles.btn} disabled={loading}>
              {loading ? (
                <><span style={styles.spinner}/> Looking up devices...</>
              ) : (
                <><svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
                  <path d="M9.5 9.5l3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>Preview Devices to Release</>
              )}
            </button>
          </form>

          {successMsg && (
            <div style={styles.success}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="6" stroke="var(--accent-green)" strokeWidth="1.2"/>
                <path d="M4 7l2 2 4-4" stroke="var(--accent-green)" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              {successMsg}
            </div>
          )}

          {preview?.device_count > 0 && (
            <div style={styles.previewSection}>
              <div style={styles.previewHeader}>
                <span style={styles.previewCount}>
                  {preview.device_count} device{preview.device_count !== 1 ? 's' : ''} found
                </span>
                <span style={styles.previewFor}>
                  assigned to <strong>{identifier}</strong>
                </span>
              </div>
              <DataTable data={preview.devices} />

              {isAdmin ? (
                <div style={styles.confirmArea}>
                  <div style={styles.confirmWarning}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path d="M7 1l6 11H1L7 1z" stroke="var(--accent-amber)" strokeWidth="1.2" strokeLinejoin="round"/>
                      <path d="M7 6v3M7 10v.5" stroke="var(--accent-amber)" strokeWidth="1.2" strokeLinecap="round"/>
                    </svg>
                    This will move all devices to <strong>IT Stock {newLocation}</strong>. This action cannot be undone.
                  </div>
                  <div style={styles.confirmBtns}>
                    <button style={styles.btnDanger} onClick={handleConfirm} disabled={releasing}>
                      {releasing ? 'Releasing...' : '✓ Confirm Release'}
                    </button>
                    <button style={styles.btnGhost} onClick={() => setPreview(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={styles.viewerNote}>
                  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                    <circle cx="6.5" cy="6.5" r="5.5" stroke="var(--text-muted)" strokeWidth="1.1"/>
                    <path d="M6.5 5v4M6.5 3.5v.5" stroke="var(--text-muted)" strokeWidth="1.1" strokeLinecap="round"/>
                  </svg>
                  Admin role required to confirm release
                </div>
              )}
            </div>
          )}

          {preview?.device_count === 0 && (
            <div style={styles.noDevices}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6.5" stroke="var(--text-muted)" strokeWidth="1.2"/>
                <path d="M5 8h6" stroke="var(--text-muted)" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              No assigned devices found for "{identifier}"
            </div>
          )}
        </div>

        {/* Stock Table */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardIconWrap}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <rect x="2" y="2" width="12" height="12" rx="2" stroke="var(--accent-green)" strokeWidth="1.3"/>
                <path d="M5 8h6M8 5v6" stroke="var(--accent-green)" strokeWidth="1.3" strokeLinecap="round"/>
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <div style={styles.cardTitle}>Current IT Stock</div>
              <div style={styles.cardSub}>All unassigned devices available for allocation</div>
            </div>
            {stock && (
              <span style={styles.stockBadge}>{stock.total} units</span>
            )}
          </div>
          <div style={{ padding: 0 }}>
            {stockLoading ? (
              <div style={styles.loadingText}>Loading stock...</div>
            ) : stock?.records?.length > 0 ? (
              <DataTable data={stock.records} />
            ) : (
              <div style={styles.emptyStock}>No items currently in IT Stock</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', background: 'var(--bg-base)' },
  header: {
    padding: '18px 28px 14px',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0, background: 'var(--bg-surface)',
    boxShadow: 'var(--shadow-sm)',
  },
  title: { fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 },
  subtitle: { fontSize: 12.5, color: 'var(--text-secondary)' },
  body: { padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 20 },
  card: {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 16, overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '16px 18px',
    borderBottom: '1px solid var(--border)', background: 'var(--bg-elevated)',
  },
  cardIconWrap: {
    width: 34, height: 34, borderRadius: 10, background: 'var(--bg-surface)',
    border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  cardTitle: { fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)' },
  cardSub:   { fontSize: 11.5, color: 'var(--text-muted)', marginTop: 1 },
  form: { padding: '18px 18px 14px', display: 'flex', flexDirection: 'column', gap: 14 },
  formRow: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  fieldGroup: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' },
  input: {
    background: 'var(--bg-elevated)', border: '1.5px solid var(--border)',
    borderRadius: 10, padding: '10px 13px', color: 'var(--text-primary)',
    fontSize: 13.5, outline: 'none', fontFamily: 'var(--font-body)',
    transition: 'border-color 0.15s',
  },
  select: {
    background: 'var(--bg-elevated)', border: '1.5px solid var(--border)',
    borderRadius: 10, padding: '10px 13px', color: 'var(--text-primary)',
    fontSize: 13.5, outline: 'none', fontFamily: 'var(--font-body)',
  },
  btn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    background: 'linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-orange-dark) 100%)',
    color: '#fff', border: 'none', borderRadius: 10,
    padding: '11px 20px', fontSize: 13.5, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'var(--font-display)',
    boxShadow: '0 3px 10px var(--accent-orange-glow)',
  },
  spinner: {
    width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff', borderRadius: '50%', display: 'inline-block',
  },
  success: {
    margin: '0 18px 16px', display: 'flex', alignItems: 'center', gap: 8,
    background: 'var(--accent-green-dim)', border: '1px solid rgba(22,163,74,0.2)',
    borderRadius: 10, padding: '10px 14px', color: 'var(--accent-green)', fontSize: 13,
  },
  previewSection: { borderTop: '1px solid var(--border)' },
  previewHeader: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
    background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border)',
  },
  previewCount: {
    fontSize: 12, fontWeight: 600, color: 'var(--accent-orange)',
    background: 'var(--accent-orange-dim)', padding: '3px 10px',
    borderRadius: 20, border: '1px solid rgba(249,115,22,0.2)',
  },
  previewFor: { fontSize: 13, color: 'var(--text-secondary)' },
  confirmArea: { padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10 },
  confirmWarning: {
    display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13,
    color: 'var(--accent-amber)', background: 'var(--accent-amber-dim)',
    border: '1px solid rgba(217,119,6,0.2)', borderRadius: 10, padding: '10px 14px', lineHeight: 1.5,
  },
  confirmBtns: { display: 'flex', gap: 10 },
  btnDanger: {
    background: 'var(--accent-red)', color: '#fff', border: 'none',
    borderRadius: 10, padding: '10px 20px', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'var(--font-display)',
  },
  btnGhost: {
    background: 'var(--bg-elevated)', color: 'var(--text-secondary)',
    border: '1.5px solid var(--border)', borderRadius: 10,
    padding: '10px 20px', fontSize: 13, cursor: 'pointer', fontFamily: 'var(--font-body)',
  },
  viewerNote: {
    display: 'flex', alignItems: 'center', gap: 7, margin: '12px 16px',
    fontSize: 12.5, color: 'var(--text-muted)', padding: '9px 13px',
    background: 'var(--bg-elevated)', borderRadius: 8, border: '1px solid var(--border)',
  },
  noDevices: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '14px 18px', fontSize: 13.5, color: 'var(--text-muted)', fontStyle: 'italic',
  },
  stockBadge: {
    fontSize: 12, color: 'var(--accent-green)', background: 'var(--accent-green-dim)',
    padding: '3px 12px', borderRadius: 20, fontWeight: 600,
    border: '1px solid rgba(22,163,74,0.2)',
  },
  loadingText: { padding: '20px 18px', color: 'var(--text-muted)', fontSize: 13 },
  emptyStock: { padding: '20px 18px', color: 'var(--text-muted)', fontSize: 13.5, fontStyle: 'italic' },
};
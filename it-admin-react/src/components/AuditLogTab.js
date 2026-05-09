import React, { useState, useEffect } from 'react';
import api from '../utils/api';

export default function AuditLogTab() {
  const [data,    setData]    = useState(null);
  const [limit,   setLimit]   = useState(50);
  const [loading, setLoading] = useState(false);
  const [filter,  setFilter]  = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/audit-log?limit=${limit}`);
      setData(res.data);
    } catch {
      setData({ entries: [], count: 0 });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [limit]);

  const entries  = data?.entries || [];
  const filtered = filter
    ? entries.filter(e =>
        e.original_query?.toLowerCase().includes(filter.toLowerCase()) ||
        e.username?.toLowerCase().includes(filter.toLowerCase()) ||
        e.query_type?.toLowerCase().includes(filter.toLowerCase())
      )
    : entries;

  const high     = entries.filter(e => e.confidence === 'high').length;
  const low      = entries.filter(e => e.confidence === 'low').length;
  const zeroRows = entries.filter(e => parseInt(e.row_count) === 0).length;

  const confStyle = (c) => {
    if (c === 'high')   return { bg: 'var(--accent-green-dim)',  color: 'var(--accent-green)' };
    if (c === 'medium') return { bg: 'var(--accent-amber-dim)',  color: 'var(--accent-amber)' };
    if (c === 'low')    return { bg: 'var(--accent-red-dim)',    color: 'var(--accent-red)'   };
    return { bg: 'var(--bg-elevated)', color: 'var(--text-muted)' };
  };

  const downloadCSV = () => {
    if (!filtered.length) return;
    const keys = Object.keys(filtered[0]);
    const csv = [
      keys.join(','),
      ...filtered.map(r => keys.map(k => `"${(r[k] ?? '').toString().replace(/"/g, '""')}"`).join(',')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'audit_log.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <h2 style={styles.title}>Audit Log</h2>
        <p style={styles.subtitle}>Recent queries, SQL generated, and confidence levels</p>
      </div>

      <div style={styles.body}>
        {/* Stats row */}
        <div style={styles.statsRow}>
          <StatPill label="Total Queries"   value={entries.length} />
          <StatPill label="High Confidence" value={high}     color="green" />
          <StatPill label="Low Confidence"  value={low}      color={low  > 0 ? 'red'   : 'default'} />
          <StatPill label="Zero Results"    value={zeroRows} color={zeroRows > 0 ? 'amber' : 'default'} />
        </div>

        {/* Toolbar */}
        <div style={styles.toolbar}>
          <div style={styles.searchWrap}>
            <svg style={styles.searchIcon} width="13" height="13" viewBox="0 0 13 13" fill="none">
              <circle cx="5.5" cy="5.5" r="4" stroke="var(--text-muted)" strokeWidth="1.2"/>
              <path d="M9 9l2.5 2.5" stroke="var(--text-muted)" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            <input
              style={styles.search}
              placeholder="Filter by query, user, or type..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
            />
          </div>
          <div style={styles.toolbarRight}>
            <select style={styles.select} value={limit} onChange={e => setLimit(Number(e.target.value))}>
              {[25, 50, 100, 200].map(n => <option key={n} value={n}>Show {n}</option>)}
            </select>
            <button style={styles.refreshBtn} onClick={load} disabled={loading}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M10 6A4 4 0 112 6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                <path d="M10 3v3h-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              {loading ? 'Loading...' : 'Refresh'}
            </button>
            <button style={styles.downloadBtn} onClick={downloadCSV}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 1v7M3.5 5.5L6 8l2.5-2.5M1 10h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Export CSV
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div style={styles.loadingText}>Loading audit log...</div>
        ) : filtered.length === 0 ? (
          <div style={styles.emptyText}>No entries found</div>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.headRow}>
                  {['Timestamp', 'User', 'Role', 'Query', 'Type', 'Rows', 'Confidence', 'Path', 'SQL', 'Answer Preview'].map(col => (
                    <th key={col} style={styles.th}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((e, i) => {
                  const cc = confStyle(e.confidence);
                  return (
                    <tr key={i} style={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                      <td style={styles.td}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                          {e.timestamp ? new Date(e.timestamp).toLocaleString() : '—'}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.userBadge}>{e.username || '—'}</span>
                      </td>
                      <td style={styles.td}>
                        <span style={{ ...styles.roleBadge, ...(e.user_role === 'admin' ? styles.adminRole : {}) }}>
                          {e.user_role}
                        </span>
                      </td>
                      <td style={{ ...styles.td, maxWidth: 240 }}>
                        <span style={{ fontSize: 12.5, color: 'var(--text-primary)', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 220 }} title={e.original_query}>
                          {e.original_query || '—'}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <span style={styles.typeBadge}>{e.query_type || '—'}</span>
                      </td>
                      <td style={styles.td}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: parseInt(e.row_count) === 0 ? 'var(--text-muted)' : 'var(--accent-green)', fontWeight: 600 }}>
                          {e.row_count ?? '—'}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <span style={{ ...styles.confBadge, background: cc.bg, color: cc.color }}>
                          {e.confidence || '—'}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {e.path_taken || '—'}
                        </span>
                      </td>
                      <td style={{ ...styles.td, maxWidth: 200 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--accent-blue)', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180 }} title={e.sql_generated}>
                          {e.sql_generated ? e.sql_generated.replace(/\s+/g, ' ').slice(0, 60) + (e.sql_generated.length > 60 ? '…' : '') : '—'}
                        </span>
                      </td>
                      <td style={{ ...styles.td, maxWidth: 200 }}>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180 }} title={e.answer_preview}>
                          {e.answer_preview || '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div style={styles.count}>
          {filtered.length} entries shown{filter ? ` (filtered from ${entries.length})` : ''}
        </div>
      </div>
    </div>
  );
}

function StatPill({ label, value, color }) {
  const map = {
    green:   { val: 'var(--accent-green)',  bg: 'var(--accent-green-dim)'  },
    red:     { val: 'var(--accent-red)',    bg: 'var(--accent-red-dim)'    },
    amber:   { val: 'var(--accent-amber)',  bg: 'var(--accent-amber-dim)'  },
    default: { val: 'var(--text-primary)',  bg: 'var(--bg-elevated)'       },
  };
  const c = map[color] || map.default;
  return (
    <div style={{ background: c.bg, border: '1px solid var(--border)', borderRadius: 12, padding: '14px 18px', minWidth: 130, boxShadow: 'var(--shadow-sm)' }}>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 26, color: c.val, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>{label}</div>
    </div>
  );
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', background: 'var(--bg-base)' },
  header: {
    padding: '18px 28px 14px', borderBottom: '1px solid var(--border)',
    flexShrink: 0, background: 'var(--bg-surface)', boxShadow: 'var(--shadow-sm)',
  },
  title:    { fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 },
  subtitle: { fontSize: 12.5, color: 'var(--text-secondary)' },
  body: { padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 16 },
  statsRow: { display: 'flex', gap: 10, flexWrap: 'wrap' },
  toolbar:  { display: 'flex', alignItems: 'center', gap: 10 },
  searchWrap: { flex: 1, position: 'relative' },
  searchIcon: { position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' },
  search: {
    width: '100%', paddingLeft: 34,
    background: 'var(--bg-surface)', border: '1.5px solid var(--border)', borderRadius: 10,
    padding: '9px 14px 9px 34px', color: 'var(--text-primary)', fontSize: 13.5,
    outline: 'none', fontFamily: 'var(--font-body)', boxShadow: 'var(--shadow-sm)',
  },
  toolbarRight: { display: 'flex', gap: 8 },
  select: {
    background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 9,
    padding: '8px 11px', color: 'var(--text-secondary)', fontSize: 13, outline: 'none',
    fontFamily: 'var(--font-body)',
  },
  refreshBtn: {
    display: 'flex', alignItems: 'center', gap: 6,
    background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 9,
    padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer',
    fontFamily: 'var(--font-body)',
  },
  downloadBtn: {
    display: 'flex', alignItems: 'center', gap: 6,
    background: 'var(--accent-orange-dim)', border: '1px solid rgba(249,115,22,0.25)',
    borderRadius: 9, padding: '8px 14px', color: 'var(--accent-orange)',
    fontSize: 13, cursor: 'pointer', fontFamily: 'var(--font-body)', fontWeight: 500,
  },
  loadingText: { padding: 20, color: 'var(--text-muted)', fontSize: 13 },
  emptyText:   { padding: 20, color: 'var(--text-muted)', fontSize: 13, fontStyle: 'italic' },
  tableWrap: {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 14, overflow: 'auto', maxHeight: 520,
    boxShadow: 'var(--shadow-sm)',
  },
  table:   { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 },
  headRow: { background: 'var(--bg-elevated)' },
  th: {
    padding: '9px 14px', textAlign: 'left', fontSize: 10.5, fontWeight: 700,
    color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em',
    borderBottom: '2px solid var(--border)', position: 'sticky', top: 0,
    background: 'var(--bg-elevated)', whiteSpace: 'nowrap',
  },
  td:      { padding: '8px 14px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' },
  rowEven: { background: 'var(--bg-surface)' },
  rowOdd:  { background: 'var(--bg-elevated)' },
  userBadge:  { fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' },
  roleBadge: {
    fontSize: 11, padding: '2px 8px', borderRadius: 20,
    background: 'var(--bg-hover)', color: 'var(--text-muted)', fontWeight: 500,
  },
  adminRole: { background: 'var(--accent-orange-dim)', color: 'var(--accent-orange)' },
  typeBadge: {
    fontSize: 11, padding: '2px 8px', borderRadius: 6,
    background: 'var(--bg-elevated)', color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)', border: '1px solid var(--border)',
  },
  confBadge:  { fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600 },
  count: { fontSize: 12, color: 'var(--text-muted)', textAlign: 'right', marginTop: 2 },
};
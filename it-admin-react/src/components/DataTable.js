import React, { useState } from 'react';

const MAX_ROWS = 50;

export default function DataTable({ data }) {
  const [page, setPage] = useState(0);
  if (!data || !data.length) return null;

  const cols      = Object.keys(data[0]);
  const pageSize  = 15;
  const totalPages = Math.ceil(Math.min(data.length, MAX_ROWS) / pageSize);
  const slice     = data.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div style={styles.wrapper}>
      <div style={styles.scroll}>
        <table style={styles.table}>
          <thead>
            <tr style={styles.headRow}>
              {cols.map(c => (
                <th key={c} style={styles.th}>{c.replace(/_/g, ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((row, i) => (
              <tr key={i} style={i % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                {cols.map(c => (
                  <td key={c} style={styles.td}>
                    <span style={getCellStyle(c, row[c])}>{row[c] ?? '—'}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div style={styles.pagination}>
          <button style={styles.pageBtn} disabled={page === 0} onClick={() => setPage(p => p - 1)}>‹</button>
          <span style={styles.pageInfo}>Page {page + 1} of {totalPages}</span>
          <button style={styles.pageBtn} disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>›</button>
          {data.length > MAX_ROWS && (
            <span style={styles.truncNote}>Showing first {MAX_ROWS} of {data.length} rows</span>
          )}
        </div>
      )}
    </div>
  );
}

function getCellStyle(col, val) {
  if (!val || val === '—') return { color: 'var(--text-dim)' };
  const colL = col.toLowerCase();

  if (colL === 'is_assigned') {
    const assigned = val?.toLowerCase() === 'true';
    return {
      fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20,
      background: assigned ? 'var(--accent-green-dim)' : 'rgba(139,145,168,0.08)',
      color: assigned ? 'var(--accent-green)' : 'var(--text-muted)',
      border: `1px solid ${assigned ? 'rgba(22,163,74,0.2)' : 'var(--border)'}`,
    };
  }
  if (colL === 'os') {
    const map = {
      'windows 10': { color: 'var(--accent-amber)', bg: 'var(--accent-amber-dim)' },
      'windows 11': { color: 'var(--accent-blue)',  bg: 'var(--accent-blue-dim)'  },
      'linux':      { color: 'var(--accent-green)', bg: 'var(--accent-green-dim)' },
      'macos':      { color: 'var(--text-secondary)', bg: 'var(--bg-hover)'       },
    };
    const m = map[val?.toLowerCase()];
    if (m) return {
      fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 20,
      ...m, border: '1px solid transparent',
    };
  }
  if (colL === 'type') {
    return {
      fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 20,
      background: 'var(--accent-orange-dim)', color: 'var(--accent-orange)',
      border: '1px solid rgba(249,115,22,0.15)',
    };
  }
  if (colL.includes('serial') || colL === 'host_name' || colL === 'employee_code') {
    return { fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--accent-blue)' };
  }
  return { color: 'var(--text-primary)' };
}

const styles = {
  wrapper: { display: 'flex', flexDirection: 'column' },
  scroll: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 },
  headRow: { background: 'var(--bg-elevated)' },
  th: {
    padding: '8px 14px', textAlign: 'left', fontSize: 10.5, fontWeight: 700,
    color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em',
    whiteSpace: 'nowrap', borderBottom: '2px solid var(--border)',
    position: 'sticky', top: 0, background: 'var(--bg-elevated)',
  },
  td: {
    padding: '8px 14px', color: 'var(--text-primary)',
    whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)',
  },
  rowEven: { background: 'var(--bg-surface)' },
  rowOdd:  { background: 'var(--bg-elevated)' },
  pagination: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '9px 14px',
    borderTop: '1px solid var(--border)', background: 'var(--bg-elevated)',
  },
  pageBtn: {
    width: 28, height: 28, borderRadius: 8, background: 'var(--bg-surface)',
    border: '1px solid var(--border)', color: 'var(--text-secondary)',
    cursor: 'pointer', fontSize: 14, fontWeight: 600,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  pageInfo: { fontSize: 12, color: 'var(--text-muted)' },
  truncNote: { marginLeft: 8, fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' },
};
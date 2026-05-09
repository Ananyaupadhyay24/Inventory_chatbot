import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

// Inline Netsmartz logo as SVG-based wordmark fallback + img tag
// Logo is passed as logoSrc prop from Dashboard

const NAV_ICONS = {
  chat: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v7a1 1 0 01-1 1H9l-3 2v-2H3a1 1 0 01-1-1V3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
      <path d="M5 6h6M5 8.5h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  release: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="9" height="10" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M9 6h3.5M9 10h3.5M10.5 4.5l2 1.5-2 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  analytics: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 13l3.5-4 3 2.5L12 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="12" cy="5" r="1.5" fill="currentColor"/>
    </svg>
  ),
  audit: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M4 4h8M4 7h8M4 10h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  ),
};

const QUERIES = {
  'Asset Lookup': ['What machine does Anjali Garg have?', 'Show details for employee NTZ2186', 'Who is using host NTZ-LAP-045?', 'Which assets are under PO PORD/00217?'],
  'Stock & Faults': ['Show all machines in IT Stock', 'List all faulty or repair devices', 'How many spare laptops are available?'],
  'OS & Hardware': ['Which machines still run Windows 10?', 'Show machines with less than 16GB RAM', 'List all Lenovo E14 laptops', 'How many Dell vs Lenovo devices?'],
  'Compliance': ['Which laptops are missing an agreement?', 'How many laptops have no agreement document?'],
  'Reports': ['Give me the full inventory summary', 'Asset count broken down by location', 'Are there any duplicate serial numbers?'],
};

export default function Sidebar({ stats, health, activeTab, setActiveTab, tabs, role, username, logoSrc }) {
  const { logout } = useAuth();
  const [expandedGroup, setExpandedGroup] = useState(null);

  const handleQueryClick = (q) => {
    window.dispatchEvent(new CustomEvent('quickQuery', { detail: q }));
    setActiveTab('chat');
  };

  return (
    <aside style={styles.sidebar}>
      {/* Orange accent top strip */}
      <div style={styles.topStrip} />

      {/* Header with logo */}
      <div style={styles.header}>
        <div style={styles.logoRow}>
          {logoSrc ? (
            <img src={logoSrc} alt="Netsmartz" style={styles.logoImg} />
          ) : (
            <div style={styles.logoFallback}>
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                <rect width="22" height="22" rx="5" fill="#f97316"/>
                <path d="M5 7h5v8H5zM12 7h5v4h-5zM12 14h5v1h-5z" fill="white"/>
              </svg>
              <span style={styles.logoText}>netsmartz</span>
            </div>
          )}
        </div>
        <div style={styles.systemBadge}>IT Inventory System</div>
      </div>

      {/* Navigation */}
      <nav style={styles.nav}>
        <div style={styles.navLabel}>Navigation</div>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{ ...styles.navItem, ...(activeTab === tab.id ? styles.navActive : {}) }}
          >
            <span style={{ ...styles.navIcon, ...(activeTab === tab.id ? styles.navIconActive : {}) }}>
              {NAV_ICONS[tab.icon]}
            </span>
            <span style={styles.navLabel2}>{tab.label}</span>
            {activeTab === tab.id && <span style={styles.navPip} />}
          </button>
        ))}
      </nav>

      <div style={styles.divider} />

      {/* Live Stats */}
      {stats && (
        <div style={styles.statsSection}>
          <div style={styles.sectionLabel}>Live Stats</div>
          <div style={styles.statsGrid}>
            <StatCard label="Total Assets" value={stats.total} />
            <StatCard label="In Stock" value={stats.in_stock} color="green" />
            <StatCard label="Laptops" value={stats.laptops} color="orange" />
            <StatCard label="Faulty" value={stats.faulty} color={stats.faulty > 0 ? 'red' : 'default'} />
          </div>
          {(stats.missing_agreement > 0 || stats.windows_10 > 0 || stats.missing_serial > 0) && (
            <div style={styles.alerts}>
              {stats.missing_agreement > 0 && <Alert text={`${stats.missing_agreement} missing agreements`} type="warn" />}
              {stats.windows_10 > 0 && <Alert text={`${stats.windows_10} on Win10`} type="warn" />}
              {stats.missing_serial > 0 && <Alert text={`${stats.missing_serial} missing serials`} type="info" />}
            </div>
          )}
        </div>
      )}

      {/* Health status */}
      {health && (
        <div style={styles.healthRow}>
          <span style={{ ...styles.healthDot, background: health.status === 'ok' ? 'var(--accent-green)' : 'var(--accent-red)' }} />
          <span style={styles.healthText}>
            {health.status === 'ok' ? `API online · ${health.chroma_indexed} vectors` : 'API offline'}
          </span>
        </div>
      )}

      <div style={styles.divider} />

      {/* Quick Queries */}
      <div style={styles.quickSection}>
        <div style={styles.sectionLabel}>Quick Queries</div>
        {Object.entries(QUERIES).map(([group, qs]) => (
          <div key={group}>
            <button
              style={styles.groupToggle}
              onClick={() => setExpandedGroup(expandedGroup === group ? null : group)}
            >
              <span>{group}</span>
              <svg
                width="10" height="10" viewBox="0 0 10 10" fill="none"
                style={{ transition: 'transform 0.2s', transform: expandedGroup === group ? 'rotate(180deg)' : 'none', flexShrink: 0 }}
              >
                <path d="M2 3.5l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            {expandedGroup === group && (
              <div style={styles.queryList}>
                {qs.map(q => (
                  <button key={q} style={styles.queryItem} onClick={() => handleQueryClick(q)}>
                    <span style={styles.queryArrow}>›</span>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer / User */}
      <div style={styles.footer}>
        <div style={styles.userRow}>
          <div style={styles.avatar}>{username?.[0]?.toUpperCase()}</div>
          <div style={styles.userInfo}>
            <div style={styles.userName}>{username}</div>
            <div style={styles.userRole}>{role}</div>
          </div>
          <button style={styles.logoutBtn} onClick={logout} title="Sign out">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5 2H2.5A1.5 1.5 0 001 3.5v7A1.5 1.5 0 002.5 12H5M9 4l3 3-3 3M13 7H5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}

function StatCard({ label, value, color }) {
  const colorMap = {
    green:  { val: 'var(--accent-green)',  bg: 'var(--accent-green-dim)' },
    red:    { val: 'var(--accent-red)',    bg: 'var(--accent-red-dim)' },
    orange: { val: 'var(--accent-orange)', bg: 'var(--accent-orange-dim)' },
    default:{ val: 'var(--text-primary)',  bg: 'var(--bg-elevated)' },
  };
  const c = colorMap[color] || colorMap.default;
  return (
    <div style={{ ...styles.statCard, background: c.bg }}>
      <div style={{ ...styles.statValue, color: c.val }}>{value ?? '—'}</div>
      <div style={styles.statLabel}>{label}</div>
    </div>
  );
}

function Alert({ text, type }) {
  const color = type === 'warn' ? 'var(--accent-amber)' : 'var(--accent-blue)';
  const bg    = type === 'warn' ? 'var(--accent-amber-dim)' : 'var(--accent-blue-dim)';
  return (
    <div style={{ ...styles.alert, background: bg, color }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color, display: 'inline-block', marginRight: 6, flexShrink: 0 }} />
      {text}
    </div>
  );
}

const styles = {
  sidebar: {
    width: 268, minWidth: 268, height: '100vh',
    background: 'var(--bg-surface)',
    borderRight: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: 'var(--shadow-sm)',
  },
  topStrip: {
    height: 4,
    background: 'linear-gradient(90deg, #f97316 0%, #fb923c 60%, #fdba74 100%)',
    flexShrink: 0,
  },
  header: { padding: '16px 16px 12px', borderBottom: '1px solid var(--border)' },
  logoRow: { marginBottom: 6 },
  logoImg: { height: 100, objectFit: 'contain', maxWidth: '100%' },
  logoFallback: { display: 'flex', alignItems: 'center', gap: 8 },
  logoText: { fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' },
  systemBadge: {
    display: 'inline-block', fontSize: 10.5, fontWeight: 500,
    color: 'var(--accent-orange)', background: 'var(--accent-orange-dim)',
    padding: '2px 8px', borderRadius: 20, letterSpacing: '0.02em',
  },
  nav: { padding: '12px 10px 6px' },
  navLabel: {
    fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.1em',
    padding: '0 6px', marginBottom: 6,
  },
  navLabel2: { flex: 1 },
  navItem: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '9px 10px', borderRadius: 10,
    color: 'var(--text-secondary)', fontSize: 13.5, fontWeight: 400,
    cursor: 'pointer', transition: 'all 0.13s',
    background: 'none', border: 'none', textAlign: 'left', width: '100%',
    position: 'relative', marginBottom: 2,
  },
  navActive: {
    background: 'var(--accent-orange-dim)',
    color: 'var(--accent-orange)',
    fontWeight: 600,
  },
  navIcon: { display: 'flex', alignItems: 'center', flexShrink: 0, color: 'var(--text-muted)' },
  navIconActive: { color: 'var(--accent-orange)' },
  navPip: {
    width: 6, height: 6, borderRadius: '50%',
    background: 'var(--accent-orange)', marginLeft: 'auto',
  },
  divider: { height: 1, background: 'var(--border)', margin: '6px 0' },
  statsSection: { padding: '8px 12px 4px' },
  sectionLabel: {
    fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.1em',
    marginBottom: 8, paddingLeft: 4,
  },
  statsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 },
  statCard: {
    borderRadius: 10, padding: '9px 11px',
    border: '1px solid var(--border)',
  },
  statValue: { fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, lineHeight: 1.1 },
  statLabel: { fontSize: 10.5, color: 'var(--text-muted)', marginTop: 2 },
  alerts: { display: 'flex', flexDirection: 'column', gap: 4 },
  alert: { fontSize: 11, borderRadius: 6, padding: '5px 8px', display: 'flex', alignItems: 'center' },
  healthRow: {
    display: 'flex', alignItems: 'center', gap: 7,
    padding: '5px 16px 8px',
  },
  healthDot: { width: 6, height: 6, borderRadius: '50%', flexShrink: 0 },
  healthText: { fontSize: 11, color: 'var(--text-muted)' },
  quickSection: { flex: 1, overflow: 'auto', padding: '4px 10px' },
  groupToggle: {
    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '7px 8px', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)',
    cursor: 'pointer', background: 'none', border: 'none', borderRadius: 8,
    transition: 'color 0.12s', textAlign: 'left', gap: 6,
  },
  queryList: { paddingBottom: 2 },
  queryItem: {
    display: 'flex', alignItems: 'flex-start', gap: 6,
    width: '100%', textAlign: 'left',
    padding: '5px 8px', fontSize: 11.5, color: 'var(--text-muted)',
    background: 'none', border: 'none', cursor: 'pointer', borderRadius: 6,
    transition: 'color 0.12s, background 0.12s', lineHeight: 1.45,
  },
  queryArrow: { color: 'var(--accent-orange)', fontWeight: 700, flexShrink: 0, marginTop: 1 },
  footer: { borderTop: '1px solid var(--border)', padding: '12px 14px' },
  userRow: { display: 'flex', alignItems: 'center', gap: 10 },
  avatar: {
    width: 32, height: 32, borderRadius: '50%',
    background: 'linear-gradient(135deg, var(--accent-orange), #fb923c)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, color: '#fff',
    flexShrink: 0, boxShadow: '0 2px 8px var(--accent-orange-glow)',
  },
  userInfo: { flex: 1, minWidth: 0 },
  userName: { fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.2 },
  userRole: {
    fontSize: 10.5, color: 'var(--accent-orange)', fontWeight: 500,
    textTransform: 'capitalize', marginTop: 1,
  },
  logoutBtn: {
    padding: 6, color: 'var(--text-muted)', cursor: 'pointer',
    background: 'none', border: 'none', borderRadius: 6,
    display: 'flex', alignItems: 'center', transition: 'color 0.12s',
  },
};
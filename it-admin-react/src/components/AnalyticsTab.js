import React, { useState } from 'react';
import api from '../utils/api';
import DataTable from './DataTable';

export default function AnalyticsTab() {
  return (
    <div style={styles.root}>
      <div style={styles.header}>
        <h2 style={styles.title}>Analytics & Procurement</h2>
        <p style={styles.subtitle}>Stock forecasting, gap analysis, and AI-powered procurement suggestions</p>
      </div>
      <div style={styles.body}>
        <SmartPrediction />
        <GapAnalysis />
        <Procurement />
      </div>
    </div>
  );
}

function SmartPrediction() {
  const [joiners,    setJoiners]    = useState(10);
  const [department, setDepartment] = useState('');
  const [categories, setCategories] = useState([]);
  const [result,     setResult]     = useState(null);
  const [loading,    setLoading]    = useState(false);

  const toggleCat = (c) => setCategories(prev =>
    prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]
  );

  const run = async () => {
    setLoading(true);
    try {
      const res = await api.post('/analytics/smart-predict', {
        new_joiners: parseInt(joiners), department: department.trim(), categories,
      });
      setResult(res.data);
    } catch (err) {
      alert(err.response?.data?.detail || 'Prediction failed');
    } finally { setLoading(false); }
  };

  const priorityMap = {
    High:   { color: 'var(--accent-red)',    bg: 'var(--accent-red-dim)',    icon: '🔴' },
    Medium: { color: 'var(--accent-amber)',  bg: 'var(--accent-amber-dim)',  icon: '🟡' },
    Low:    { color: 'var(--accent-green)',  bg: 'var(--accent-green-dim)',  icon: '🟢' },
  };
  const pc = priorityMap[result?.priority] || priorityMap.Low;

  return (
    <SectionCard icon={<PredictIcon />} title="Future Requirement Prediction" subtitle="AI-reasoned device forecast for incoming hires">
      <div style={styles.controlsRow}>
        <Field label="New Joiners">
          <input type="number" min={1} max={500} style={styles.input} value={joiners} onChange={e => setJoiners(e.target.value)} />
        </Field>
        <Field label="Department (optional)">
          <input style={styles.input} value={department} onChange={e => setDepartment(e.target.value)} placeholder="e.g. Engineering, QA" />
        </Field>
        <Field label="Device Category">
          <div style={styles.catRow}>
            {['Laptop', 'Desktop', 'MAC Mini'].map(c => (
              <button key={c} style={{ ...styles.catBtn, ...(categories.includes(c) ? styles.catBtnActive : {}) }} onClick={() => toggleCat(c)}>
                {c}
              </button>
            ))}
          </div>
        </Field>
      </div>
      <button style={styles.runBtn} onClick={run} disabled={loading}>
        {loading ? <><span style={styles.spinner}/> Generating...</> : '▶ Predict Requirements'}
      </button>

      {result && (
        <div style={styles.results}>
          <div style={styles.resultsHeader}>
            <span style={styles.scopeTag}>{result.department}</span>
            <span style={styles.scopeTag}>{result.new_joiners} joiners</span>
            {result.priority && (
              <span style={{ ...styles.priorityBadge, background: pc.bg, color: pc.color }}>
                {pc.icon} {result.priority} Priority
              </span>
            )}
          </div>

          {result.per_type_gaps?.length > 0 && (
            <div style={styles.gapCards}>
              {result.per_type_gaps.map(g => <GapCard key={g.type} gap={g} />)}
            </div>
          )}

          {(result.analysis?.length > 0 || result.recommendations?.length > 0) && (
            <div style={styles.aiSection}>
              <div style={styles.aiPanel}>
                <div style={styles.aiPanelHeader}>
                  <AIIcon /> Analysis
                </div>
                <ul style={styles.bulletList}>
                  {result.analysis.map((a, i) => (
                    <li key={i} style={styles.bulletItem}>
                      <span style={styles.bulletDot} />
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
              <div style={styles.aiPanel}>
                <div style={styles.aiPanelHeader}>
                  <AIIcon /> Recommendations
                </div>
                <ul style={styles.bulletList}>
                  {result.recommendations.map((r, i) => (
                    <li key={i} style={styles.bulletItem}>
                      <span style={{ ...styles.bulletDot, background: 'var(--accent-orange)' }} />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {result.future_outlook && (
            <div style={styles.outlook}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1.5 9l3.5-4 3 3L13 2" stroke="var(--accent-orange)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{result.future_outlook}</span>
            </div>
          )}

          {result.breakdown?.length > 0 && (
            <div>
              <div style={styles.innerLabel}>Device Breakdown</div>
              <DataTable data={result.breakdown} />
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}

function GapCard({ gap }) {
  const hasShortfall = gap.shortfall > 0;
  return (
    <div style={styles.gapCard}>
      <div style={styles.gapType}>{gap.type}</div>
      <div style={styles.gapMetrics}>
        <GapMetric label="Required"      value={gap.required}          />
        <GapMetric label="Total Stock"   value={gap.available}         />
        <GapMetric label="Usable ≥16GB"  value={gap.usable_available}  />
        <GapMetric
          label={hasShortfall ? 'Shortfall' : 'Surplus'}
          value={hasShortfall ? `-${gap.shortfall}` : `+${gap.surplus}`}
          color={hasShortfall ? 'var(--accent-red)' : 'var(--accent-green)'}
        />
      </div>
    </div>
  );
}

function GapMetric({ label, value, color }) {
  return (
    <div style={styles.metric}>
      <div style={{ ...styles.metricValue, color: color || 'var(--text-primary)' }}>{value}</div>
      <div style={styles.metricLabel}>{label}</div>
    </div>
  );
}

function GapAnalysis() {
  const [joiners, setJoiners] = useState(10);
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const res = await api.post('/analytics/gap', { new_joiners: parseInt(joiners) });
      setResult(res.data);
    } catch (err) {
      alert(err.response?.data?.detail || 'Gap analysis failed');
    } finally { setLoading(false); }
  };

  return (
    <SectionCard icon={<GapIcon />} title="Stock vs Requirement Gap Analysis" subtitle="Compare current IT Stock against predicted requirements">
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
        <Field label="Expected New Joiners">
          <input type="number" min={1} max={500} style={styles.input} value={joiners} onChange={e => setJoiners(e.target.value)} />
        </Field>
        <button style={styles.runBtn} onClick={run} disabled={loading}>
          {loading ? 'Analysing...' : '▶ Run Gap Analysis'}
        </button>
      </div>
      {result && (
        <div style={styles.results}>
          <div style={result.has_shortage ? styles.bannerDanger : styles.bannerSuccess}>
            {result.has_shortage
              ? `⚠️ Shortage in: ${result.shortage_types.join(', ')}`
              : '✓ Current stock is sufficient for this intake'}
          </div>
          {result.breakdown?.length > 0 && <DataTable data={result.breakdown} />}
        </div>
      )}
    </SectionCard>
  );
}

function Procurement() {
  const [joiners, setJoiners] = useState(10);
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const res = await api.post('/analytics/procurement', { new_joiners: parseInt(joiners) });
      setResult(res.data);
    } catch (err) {
      alert(err.response?.data?.detail || 'Procurement failed');
    } finally { setLoading(false); }
  };

  return (
    <SectionCard icon={<ProcureIcon />} title="Procurement Suggestions" subtitle="Recommended models and quantities based on gap analysis">
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
        <Field label="Expected New Joiners">
          <input type="number" min={1} max={500} style={styles.input} value={joiners} onChange={e => setJoiners(e.target.value)} />
        </Field>
        <button style={styles.runBtn} onClick={run} disabled={loading}>
          {loading ? 'Generating...' : '▶ Generate Suggestions'}
        </button>
      </div>
      {result && (
        <div style={styles.results}>
          {result.sufficient ? (
            <div style={styles.bannerSuccess}>✓ Current stock is sufficient. No procurement needed.</div>
          ) : (
            <>
              <div style={styles.procureTotal}>
                <span style={styles.procureCount}>{result.total_units}</span>
                <span style={styles.procureCountLabel}>total units to procure</span>
              </div>
              {result.suggestions?.length > 0 && <DataTable data={result.suggestions} />}
            </>
          )}
        </div>
      )}
    </SectionCard>
  );
}

function SectionCard({ icon, title, subtitle, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div style={styles.sectionCard}>
      <button style={styles.sectionHeader} onClick={() => setOpen(o => !o)}>
        <div style={styles.sectionIconWrap}>{icon}</div>
        <div style={{ flex: 1, textAlign: 'left' }}>
          <div style={styles.sectionTitle}>{title}</div>
          <div style={styles.sectionSub}>{subtitle}</div>
        </div>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
          style={{ transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'none', flexShrink: 0, color: 'var(--text-muted)' }}>
          <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && <div style={styles.sectionBody}>{children}</div>}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={styles.field}>
      <label style={styles.label}>{label}</label>
      {children}
    </div>
  );
}

function AIIcon() {
  return <svg width="13" height="13" viewBox="0 0 13 13" fill="none" style={{ color: 'var(--accent-orange)' }}>
    <rect x="1" y="3" width="4" height="7" rx="1" stroke="currentColor" strokeWidth="1"/>
    <rect x="7" y="3" width="5" height="3" rx="1" stroke="currentColor" strokeWidth="1"/>
    <rect x="7" y="8" width="5" height="2" rx="1" stroke="currentColor" strokeWidth="1"/>
  </svg>;
}
function PredictIcon() {
  return <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
    <path d="M1.5 11.5l3.5-5 3 3 4.5-7" stroke="var(--accent-orange)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="12.5" cy="3.5" r="1.2" fill="var(--accent-orange)"/>
  </svg>;
}
function GapIcon() {
  return <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
    <rect x="1.5" y="5" width="4" height="8" rx="1" stroke="var(--accent-amber)" strokeWidth="1.3"/>
    <rect x="8" y="2" width="4" height="11" rx="1" stroke="var(--accent-amber)" strokeWidth="1.3"/>
  </svg>;
}
function ProcureIcon() {
  return <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
    <circle cx="5" cy="12" r="1.5" stroke="var(--accent-green)" strokeWidth="1.2"/>
    <circle cx="11" cy="12" r="1.5" stroke="var(--accent-green)" strokeWidth="1.2"/>
    <path d="M1 2h2l2.5 6.5h6l1.5-4H4" stroke="var(--accent-green)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>;
}

const styles = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', background: 'var(--bg-base)' },
  header: {
    padding: '18px 28px 14px', borderBottom: '1px solid var(--border)',
    flexShrink: 0, background: 'var(--bg-surface)', boxShadow: 'var(--shadow-sm)',
  },
  title: { fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 },
  subtitle: { fontSize: 12.5, color: 'var(--text-secondary)' },
  body: { padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 18 },
  sectionCard: {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 16, overflow: 'hidden', boxShadow: 'var(--shadow-sm)',
  },
  sectionHeader: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '16px 18px',
    borderBottom: '1px solid var(--border)', background: 'var(--bg-elevated)',
    cursor: 'pointer', width: '100%', border: 'none',
    borderBottom: '1px solid var(--border)',
  },
  sectionIconWrap: {
    width: 34, height: 34, borderRadius: 10,
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  sectionTitle: { fontSize: 13.5, fontWeight: 600, color: 'var(--text-primary)' },
  sectionSub:   { fontSize: 11.5, color: 'var(--text-muted)', marginTop: 1 },
  sectionBody:  { padding: 18, display: 'flex', flexDirection: 'column', gap: 14 },
  controlsRow:  { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 },
  field:  { display: 'flex', flexDirection: 'column', gap: 6 },
  label:  { fontSize: 10.5, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' },
  input:  {
    background: 'var(--bg-elevated)', border: '1.5px solid var(--border)', borderRadius: 10,
    padding: '9px 12px', color: 'var(--text-primary)', fontSize: 13.5, outline: 'none',
    fontFamily: 'var(--font-body)', width: '100%',
  },
  catRow:       { display: 'flex', gap: 6 },
  catBtn: {
    fontSize: 12, padding: '7px 11px', borderRadius: 8,
    background: 'var(--bg-elevated)', border: '1.5px solid var(--border)',
    color: 'var(--text-muted)', cursor: 'pointer', transition: 'all 0.12s',
    fontFamily: 'var(--font-body)',
  },
  catBtnActive: {
    background: 'var(--accent-orange-dim)', border: '1.5px solid rgba(249,115,22,0.3)',
    color: 'var(--accent-orange)', fontWeight: 500,
  },
  runBtn: {
    display: 'flex', alignItems: 'center', gap: 7,
    background: 'linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-orange-dark) 100%)',
    color: '#fff', border: 'none', borderRadius: 10, padding: '10px 20px',
    fontSize: 13, fontWeight: 600, cursor: 'pointer',
    fontFamily: 'var(--font-display)', whiteSpace: 'nowrap', height: 40,
    boxShadow: '0 2px 8px var(--accent-orange-glow)',
  },
  spinner: {
    width: 13, height: 13, border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#fff', borderRadius: '50%', display: 'inline-block',
  },
  results:       { display: 'flex', flexDirection: 'column', gap: 14, marginTop: 2 },
  resultsHeader: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  scopeTag: {
    fontSize: 12, fontWeight: 500, padding: '4px 12px', borderRadius: 20,
    background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-secondary)',
  },
  priorityBadge: { fontSize: 12, fontWeight: 600, padding: '4px 12px', borderRadius: 20 },
  gapCards: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))', gap: 12 },
  gapCard: {
    background: 'var(--bg-elevated)', border: '1px solid var(--border)',
    borderRadius: 12, padding: '14px 16px',
    borderTop: '3px solid var(--accent-orange)',
  },
  gapType: {
    fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)',
    marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em',
  },
  gapMetrics: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8 },
  metric:      { display: 'flex', flexDirection: 'column', gap: 3 },
  metricValue: { fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 20, lineHeight: 1 },
  metricLabel: { fontSize: 10, color: 'var(--text-muted)', fontWeight: 500 },
  aiSection:   { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  aiPanel: {
    background: 'var(--bg-elevated)', border: '1px solid var(--border)',
    borderRadius: 12, padding: '14px 16px',
  },
  aiPanelHeader: {
    display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700,
    color: 'var(--accent-orange)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em',
  },
  bulletList: { paddingLeft: 0, margin: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 7 },
  bulletItem: {
    display: 'flex', alignItems: 'flex-start', gap: 8,
    fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.55,
  },
  bulletDot: {
    width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-blue)',
    marginTop: 5, flexShrink: 0,
  },
  outlook: {
    display: 'flex', alignItems: 'flex-start', gap: 8,
    background: 'var(--accent-orange-dim)', border: '1px solid rgba(249,115,22,0.15)',
    borderRadius: 10, padding: '11px 14px',
  },
  innerLabel: {
    fontSize: 10.5, fontWeight: 700, color: 'var(--text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
  },
  bannerDanger: {
    borderRadius: 10, padding: '11px 16px', fontSize: 13, fontWeight: 500,
    background: 'var(--accent-red-dim)', border: '1px solid rgba(220,38,38,0.2)', color: 'var(--accent-red)',
  },
  bannerSuccess: {
    borderRadius: 10, padding: '11px 16px', fontSize: 13, fontWeight: 500,
    background: 'var(--accent-green-dim)', border: '1px solid rgba(22,163,74,0.2)', color: 'var(--accent-green)',
  },
  procureTotal: { display: 'flex', alignItems: 'baseline', gap: 10 },
  procureCount: { fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 40, color: 'var(--accent-orange)' },
  procureCountLabel: { fontSize: 14, color: 'var(--text-secondary)' },
};
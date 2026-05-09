import React, { useState, useEffect, useRef, useCallback } from 'react';
import api from '../utils/api';
import DataTable from './DataTable';

const STAGES = [
  'Classifying query...',
  'Extracting entities...',
  'Generating SQL...',
  'Executing query...',
  'Writing answer...',
];

export default function ChatTab() {
  const [messages, setMessages]     = useState([]);
  const [llmHistory, setLlmHistory] = useState([]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [stageIdx, setStageIdx]     = useState(0);
  const endRef     = useRef(null);
  const stageTimer = useRef(null);
  const inputRef   = useRef(null);

  useEffect(() => {
    const handler = (e) => { setInput(e.detail); inputRef.current?.focus(); };
    window.addEventListener('quickQuery', handler);
    return () => window.removeEventListener('quickQuery', handler);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const startStageLoop = useCallback(() => {
    let idx = 0;
    setStageIdx(0);
    stageTimer.current = setInterval(() => {
      idx = (idx + 1) % STAGES.length;
      setStageIdx(idx);
    }, 1800);
  }, []);

  const stopStageLoop = useCallback(() => {
    clearInterval(stageTimer.current);
  }, []);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || loading) return;
    const query = text.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setLlmHistory(prev => [...prev, { role: 'user', content: query }].slice(-20));
    setLoading(true);
    startStageLoop();

    try {
      const historyToSend = llmHistory.slice(-20);
      const res = await api.post('/chat', { query, history: historyToSend });
      const { answer, records, count } = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: answer, records, count }]);
      setLlmHistory(prev => [...prev, { role: 'assistant', content: answer }].slice(-20));
    } catch (err) {
      const errMsg = err.response?.data?.detail || 'An error occurred. Please try again.';
      setMessages(prev => [...prev, { role: 'assistant', content: errMsg, error: true }]);
    } finally {
      stopStageLoop();
      setLoading(false);
    }
  }, [loading, llmHistory, startStageLoop, stopStageLoop]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>Inventory Chat</h2>
          <p style={styles.subtitle}>Ask anything about your IT assets in natural language</p>
        </div>
        <div style={styles.headerRight}>
          <div style={styles.modelBadge}>
            <span style={styles.modelDot} />
            llama-3.3-70b
          </div>
          {messages.length > 0 && (
            <button style={styles.clearBtn} onClick={() => { setMessages([]); setLlmHistory([]); }}>
              Clear chat
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {messages.length === 0 && <EmptyState onQuery={sendMessage} />}
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {loading && (
          <div style={styles.thinkingRow}>
            <div style={styles.botAvatar}>
              <BotIcon />
            </div>
            <div style={styles.thinkingBubble}>
              <span style={styles.thinkingDot} />
              <span style={styles.thinkingText}>{STAGES[stageIdx]}</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div style={styles.inputArea}>
        <div style={styles.inputWrapper}>
          <textarea
            ref={inputRef}
            style={styles.textarea}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about any asset, employee, OS, hardware, or compliance..."
            rows={1}
            disabled={loading}
          />
          <button
            style={{ ...styles.sendBtn, ...(!input.trim() || loading ? styles.sendBtnDisabled : {}) }}
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M1.5 7.5l12-5-5 12-2-5z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" fill="currentColor" fillOpacity="0.2"/>
            </svg>
          </button>
        </div>
        <div style={styles.inputHint}>
          <span>Press Enter to send · Shift+Enter for newline</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>LangGraph · SQL + ChromaDB</span>
        </div>
      </div>
    </div>
  );
}

function BotIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <rect x="1" y="4" width="4" height="6" rx="1" stroke="currentColor" strokeWidth="1.2"/>
      <rect x="7" y="4" width="4" height="3" rx="1" stroke="currentColor" strokeWidth="1.2"/>
      <rect x="7" y="9" width="4" height="1.5" rx="0.5" stroke="currentColor" strokeWidth="1.2"/>
      <path d="M5 7h2M12 5.5h1M12 10h1" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
    </svg>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{ ...styles.msgRow, justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      {!isUser && (
        <div style={styles.botAvatar}><BotIcon /></div>
      )}
      <div style={{ maxWidth: '78%', display: 'flex', flexDirection: 'column', gap: 8, alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        <div style={{
          ...styles.bubble,
          ...(isUser ? styles.bubbleUser : styles.bubbleBot),
          ...(msg.error ? styles.bubbleError : {}),
        }}>
          <p style={{ ...styles.msgText, color: isUser ? '#fff' : 'var(--text-primary)' }}>{msg.content}</p>
        </div>
        {msg.records?.length > 0 && (
          <div style={styles.tableContainer}>
            <div style={styles.tableLabel}>
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                <rect x="0.5" y="0.5" width="10" height="10" rx="1.5" stroke="var(--accent-orange)" strokeWidth="1"/>
                <path d="M2 3.5h7M2 5.5h7M2 7.5h5" stroke="var(--accent-orange)" strokeWidth="0.9" strokeLinecap="round"/>
              </svg>
              {msg.count} record{msg.count !== 1 ? 's' : ''} found
            </div>
            <DataTable data={msg.records} />
            <DownloadBtn data={msg.records} />
          </div>
        )}
      </div>
    </div>
  );
}

function DownloadBtn({ data }) {
  const download = () => {
    if (!data.length) return;
    const keys = Object.keys(data[0]);
    const csv = [keys.join(','), ...data.map(r => keys.map(k => `"${(r[k] ?? '').toString().replace(/"/g, '""')}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'inventory_export.csv'; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button style={styles.downloadBtn} onClick={download}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M6 1v7M3.5 5.5L6 8l2.5-2.5M1 10h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
      Download CSV
    </button>
  );
}

function EmptyState({ onQuery }) {
  const suggestions = [
    { text: 'What machine does Anjali Garg have?', icon: '👤' },
    { text: 'List all Windows 10 machines',         icon: '🖥️' },
    { text: 'Show devices missing serial numbers',  icon: '⚠️' },
    { text: 'How many laptops are in IT Stock?',    icon: '📦' },
  ];
  return (
    <div style={styles.empty}>
      <div style={styles.emptyIconWrap}>
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
          <rect width="40" height="40" rx="12" fill="var(--accent-orange-dim)"/>
          <path d="M10 14a2 2 0 012-2h16a2 2 0 012 2v12a2 2 0 01-2 2H12a2 2 0 01-2-2V14z" stroke="var(--accent-orange)" strokeWidth="1.5"/>
          <path d="M15 19h10M15 22h7" stroke="var(--accent-orange)" strokeWidth="1.5" strokeLinecap="round"/>
          <circle cx="28" cy="12" r="5" fill="var(--accent-orange)" opacity="0.15"/>
          <path d="M26 12h4M28 10v4" stroke="var(--accent-orange)" strokeWidth="1.3" strokeLinecap="round"/>
        </svg>
      </div>
      <h3 style={styles.emptyTitle}>Ask about your IT inventory</h3>
      <p style={styles.emptySubtitle}>Powered by LangGraph SQL agent + ChromaDB semantic search</p>
      <div style={styles.suggestionsGrid}>
        {suggestions.map(s => (
          <button key={s.text} style={styles.suggestionBtn} onClick={() => onQuery(s.text)}>
            <span style={styles.suggestionIcon}>{s.icon}</span>
            <span>{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

const styles = {
  root: {
    display: 'flex', flexDirection: 'column', height: '100%',
    background: 'var(--bg-base)', overflow: 'hidden',
  },
  header: {
    padding: '18px 28px 14px',
    borderBottom: '1px solid var(--border)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    flexShrink: 0, background: 'var(--bg-surface)',
    boxShadow: 'var(--shadow-sm)',
  },
  title: {
    fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
    color: 'var(--text-primary)', marginBottom: 2,
  },
  subtitle: { fontSize: 12.5, color: 'var(--text-secondary)' },
  headerRight: { display: 'flex', alignItems: 'center', gap: 10 },
  modelBadge: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 11.5, fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)', background: 'var(--bg-elevated)',
    border: '1px solid var(--border)', borderRadius: 20, padding: '4px 10px',
  },
  modelDot: { width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-green)' },
  clearBtn: {
    fontSize: 12, color: 'var(--text-secondary)', background: 'var(--bg-elevated)',
    border: '1px solid var(--border)', borderRadius: 8, padding: '5px 12px', cursor: 'pointer',
  },
  messages: {
    flex: 1, overflow: 'auto', padding: '24px 28px',
    display: 'flex', flexDirection: 'column', gap: 16,
  },
  msgRow: { display: 'flex', gap: 10, alignItems: 'flex-start' },
  botAvatar: {
    width: 30, height: 30, borderRadius: 9, flexShrink: 0, marginTop: 2,
    background: 'linear-gradient(135deg, var(--accent-orange-dim), rgba(249,115,22,0.15))',
    border: '1px solid rgba(249,115,22,0.25)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--accent-orange)',
  },
  bubble: { borderRadius: 14, padding: '11px 16px', maxWidth: '100%', boxShadow: 'var(--shadow-sm)' },
  bubbleUser: {
    background: 'linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-orange-dark) 100%)',
    borderBottomRightRadius: 4,
  },
  bubbleBot: {
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderBottomLeftRadius: 4,
  },
  bubbleError: { background: 'var(--accent-red-dim)', border: '1px solid rgba(220,38,38,0.2)' },
  msgText: { fontSize: 14, lineHeight: 1.65, whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  tableContainer: {
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 12, overflow: 'hidden', width: '100%', minWidth: 420,
    boxShadow: 'var(--shadow-sm)',
  },
  tableLabel: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '8px 14px', fontSize: 11.5, color: 'var(--text-secondary)',
    borderBottom: '1px solid var(--border)', background: 'var(--bg-elevated)',
    fontWeight: 500,
  },
  downloadBtn: {
    display: 'flex', alignItems: 'center', gap: 5,
    fontSize: 11.5, color: 'var(--accent-orange)', background: 'none', border: 'none',
    cursor: 'pointer', padding: '8px 14px', borderTop: '1px solid var(--border)',
    fontWeight: 500, transition: 'opacity 0.12s',
  },
  thinkingRow: { display: 'flex', gap: 10, alignItems: 'center' },
  thinkingBubble: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'var(--bg-surface)', border: '1px solid var(--border)',
    borderRadius: 14, borderBottomLeftRadius: 4,
    padding: '9px 14px', boxShadow: 'var(--shadow-sm)',
  },
  thinkingDot: {
    width: 8, height: 8, borderRadius: '50%',
    background: 'var(--accent-orange)',
    display: 'inline-block',
    animation: 'pulse 1.2s ease-in-out infinite',
  },
  thinkingText: { fontSize: 12.5, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' },
  inputArea: {
    padding: '12px 20px 16px', borderTop: '1px solid var(--border)',
    flexShrink: 0, background: 'var(--bg-surface)',
  },
  inputWrapper: {
    display: 'flex', alignItems: 'flex-end', gap: 8,
    background: 'var(--bg-elevated)', border: '1.5px solid var(--border)',
    borderRadius: 14, padding: '9px 9px 9px 16px',
    transition: 'border-color 0.15s',
    boxShadow: 'var(--shadow-sm)',
  },
  textarea: {
    flex: 1, background: 'none', border: 'none', outline: 'none',
    color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-body)',
    resize: 'none', lineHeight: 1.6, maxHeight: 120, overflow: 'auto',
  },
  sendBtn: {
    width: 36, height: 36, borderRadius: 10, flexShrink: 0,
    background: 'linear-gradient(135deg, var(--accent-orange) 0%, var(--accent-orange-dark) 100%)',
    color: '#fff', border: 'none',
    display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
    transition: 'opacity 0.12s, transform 0.1s',
    boxShadow: '0 2px 8px var(--accent-orange-glow)',
  },
  sendBtnDisabled: { opacity: 0.35, cursor: 'not-allowed', boxShadow: 'none' },
  inputHint: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginTop: 6, fontSize: 11, color: 'var(--text-muted)', padding: '0 4px',
  },
  empty: {
    flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '40px 20px', textAlign: 'center', margin: 'auto',
  },
  emptyIconWrap: { marginBottom: 18 },
  emptyTitle: {
    fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700,
    color: 'var(--text-primary)', marginBottom: 7,
  },
  emptySubtitle: { fontSize: 13.5, color: 'var(--text-secondary)', marginBottom: 28, maxWidth: 380 },
  suggestionsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, maxWidth: 580, width: '100%' },
  suggestionBtn: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'var(--bg-surface)', border: '1.5px solid var(--border)',
    borderRadius: 12, padding: '11px 14px', fontSize: 12.5, color: 'var(--text-secondary)',
    cursor: 'pointer', textAlign: 'left', lineHeight: 1.4, transition: 'all 0.13s',
    boxShadow: 'var(--shadow-sm)',
  },
  suggestionIcon: { fontSize: 16, flexShrink: 0 },
};
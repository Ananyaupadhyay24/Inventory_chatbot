import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../utils/api';
import Sidebar from '../components/Sidebar';
import ChatTab from '../components/ChatTab';
import AssetReleaseTab from '../components/AssetReleaseTab';
import AnalyticsTab from '../components/AnalyticsTab';
import AuditLogTab from '../components/AuditLogTab';

// Netsmartz logo embedded as base64
const logoSrc = "data:image/png;base64,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";

export default function Dashboard() {
  const { auth } = useAuth();
  const [activeTab, setActiveTab] = useState('chat');
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.get('/assets/stats').then(r => setStats(r.data)).catch(() => {});
    api.get('/health').then(r => setHealth(r.data)).catch(() => {});
  }, []);

  const tabs = [
    { id: 'chat',      label: '💬 Chat',           icon: 'chat' },
    { id: 'release',   label: '📤 Asset Release',  icon: 'release' },
    { id: 'analytics', label: '📊 Analytics',      icon: 'analytics' },
    ...(auth?.role === 'admin' ? [{ id: 'audit', label: '📋 Audit Log', icon: 'audit' }] : []),
  ];

  return (
    <div style={styles.root}>
      <Sidebar
        stats={stats}
        health={health}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        tabs={tabs}
        role={auth?.role}
        username={auth?.username}
        logoSrc={logoSrc}
      />
      <main style={styles.main}>
        <div style={styles.content}>
          {activeTab === 'chat'      && <ChatTab />}
          {activeTab === 'release'   && <AssetReleaseTab />}
          {activeTab === 'analytics' && <AnalyticsTab />}
          {activeTab === 'audit'     && auth?.role === 'admin' && <AuditLogTab />}
        </div>
      </main>
    </div>
  );
}

const styles = {
  root: {
    display: 'flex',
    height: '100vh',
    overflow: 'hidden',
    background: 'var(--bg-base)',
  },
  main: {
    flex: 1,
    overflow: 'auto',
    background: 'var(--bg-base)',
  },
  content: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
  },
};
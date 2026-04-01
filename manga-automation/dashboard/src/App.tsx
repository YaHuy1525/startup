import { Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Library, Share2, Settings, Workflow, Users, Calendar, Activity } from 'lucide-react';
import MangaManager from './pages/MangaManager';
import PublisherDashboard from './pages/PublisherDashboard';
import Workflows from './pages/Workflows';
import TikTokAccounts from './pages/TikTokAccounts';
import ContentCalendar from './pages/ContentCalendar';
import Analytics from './pages/Analytics';
import { useEffect, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';

function App() {
  return (
    <div className="app-container">
      <nav className="sidebar">
        <div className="sidebar-header">
          <Share2 size={28} color="#6366f1" />
          <h1>Antigravity</h1>
        </div>

        <div className="nav-links">
          <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <LayoutDashboard size={20} />
            Overview
          </NavLink>
          <NavLink to="/manga" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Library size={20} />
            Manga Series
          </NavLink>
          <NavLink to="/publisher" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Share2 size={20} />
            TikTok Publisher
          </NavLink>
          <NavLink to="/workflows" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Workflow size={20} />
            n8n Workflows
          </NavLink>
          <NavLink to="/accounts" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Users size={20} />
            TikTok Accounts
          </NavLink>
          <NavLink to="/calendar" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Calendar size={20} />
            Content Calendar
          </NavLink>
          <NavLink to="/analytics" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Activity size={20} />
            Analytics
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Settings size={20} />
            Settings
          </NavLink>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/manga" element={<MangaManager />} />
          <Route path="/publisher" element={<PublisherDashboard />} />
          <Route path="/workflows" element={<Workflows />} />
          <Route path="/accounts" element={<TikTokAccounts />} />
          <Route path="/calendar" element={<ContentCalendar />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<div>Settings Component</div>} />
        </Routes>
      </main>
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState({
    totalManga: 0,
    videosRendered: 0,
    activeAccounts: 0,
    loading: true
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [mangaRes, videosRes, accountsRes] = await Promise.all([
          fetch(`${API_URL}/dashboard/manga`),
          fetch(`${API_URL}/dashboard/videos`),
          fetch(`${API_URL}/dashboard/tiktok-accounts`)
        ]);

        const manga = await mangaRes.json();
        const videos = await videosRes.json();
        const accounts = await accountsRes.json();

        setStats({
          totalManga: manga.manga?.length || 0,
          videosRendered: videos.videos?.length || 0,
          activeAccounts: accounts.accounts?.filter((a: any) => a.account_status === 'active').length || 0,
          loading: false
        });
      } catch (error) {
        console.error('Failed to fetch stats:', error);
        setStats(prev => ({ ...prev, loading: false }));
      }
    };

    fetchStats();
  }, []);

  if (stats.loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  return (
    <>
      <div className="header-container">
        <h2 className="page-title">Dashboard Overview</h2>
      </div>
      <div className="stats-grid">
        <div className="glass stat-card">
          <div className="stat-title">Total Manga</div>
          <div className="stat-value">{stats.totalManga}</div>
        </div>
        <div className="glass stat-card">
          <div className="stat-title">Videos Rendered</div>
          <div className="stat-value">{stats.videosRendered}</div>
        </div>
        <div className="glass stat-card">
          <div className="stat-title">Active TikTok Accounts</div>
          <div className="stat-value">{stats.activeAccounts}</div>
        </div>
      </div>
    </>
  );
}

export default App;

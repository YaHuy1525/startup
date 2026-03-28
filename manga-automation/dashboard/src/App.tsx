import { Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Library, Share2, Settings } from 'lucide-react';
import MangaManager from './pages/MangaManager';
import PublisherDashboard from './pages/PublisherDashboard';

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
          <Route path="/settings" element={<div>Settings Component</div>} />
        </Routes>
      </main>
    </div>
  );
}

function Overview() {
  return (
    <>
      <div className="header-container">
        <h2 className="page-title">Dashboard Overview</h2>
      </div>
      <div className="stats-grid">
        <div className="glass stat-card">
          <div className="stat-title">Total Manga</div>
          <div className="stat-value">24</div>
        </div>
        <div className="glass stat-card">
          <div className="stat-title">Videos Rendered</div>
          <div className="stat-value">134</div>
        </div>
        <div className="glass stat-card">
          <div className="stat-title">Active TikTok Accounts</div>
          <div className="stat-value">12</div>
        </div>
      </div>
    </>
  );
}

export default App;

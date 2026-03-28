import { useState, useEffect } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { API_BASE } from '../config';

interface Manga {
    id: number;
    title: string;
    mangadex_id: string;
    tags: string[];
    status: string;
    is_active: boolean;
    trending_score: number;
    last_published_chapter?: number;
}

export default function MangaManager() {
    const [manga, setManga] = useState<Manga[]>([]);
    const [loading, setLoading] = useState(true);
    const [showAddModal, setShowAddModal] = useState(false);

    const fetchManga = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/dashboard/manga`);
            const data = await res.json();
            setManga(data.manga);
        } catch (error) {
            console.error('Failed to fetch manga', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchManga();
    }, []);

    return (
        <>
            <div className="header-container">
                <h2 className="page-title">Manga Series Pipeline</h2>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button className="btn-secondary" onClick={fetchManga}>
                        <RefreshCw size={18} className={loading ? "spin" : ""} />
                        Refresh
                    </button>
                    <button className="btn-primary" onClick={() => setShowAddModal(true)}>
                        <Plus size={18} />
                        Add Manga
                    </button>
                </div>
            </div>

            <div className="glass table-container">
                <table className="custom-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Status</th>
                            <th>Pipeline Status</th>
                            <th>Latest Chapter</th>
                            <th>Trending Score</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={6} style={{ textAlign: 'center' }}>Loading...</td></tr>
                        ) : manga.map(item => (
                            <tr key={item.id}>
                                <td style={{ fontWeight: 500 }}>{item.title}</td>
                                <td>
                                    <span className={`badge ${item.status}`}>{item.status}</span>
                                </td>
                                <td>
                                    <span className={`badge ${item.is_active ? 'active' : 'hiatus'}`}>
                                        {item.is_active ? 'Syncing' : 'Paused'}
                                    </span>
                                </td>
                                <td>Ch {item.last_published_chapter || '-'}</td>
                                <td>{item.trending_score}</td>
                                <td>
                                    <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '13px' }}>
                                        Edit
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {manga.length === 0 && !loading && (
                            <tr><td colSpan={6} style={{ textAlign: 'center' }}>No manga series tracked yet.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {showAddModal && <AddMangaModal onClose={() => { setShowAddModal(false); fetchManga(); }} />}
        </>
    );
}

function AddMangaModal({ onClose }: { onClose: () => void }) {
    const [formData, setFormData] = useState({ title: '', mangadex_id: '' });
    const [saving, setSaving] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        await fetch(`${API_BASE}/dashboard/manga`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        setSaving(false);
        onClose();
    };

    return (
        <div className="modal-overlay">
            <div className="glass modal-content">
                <h2>Add Manga to Pipeline</h2>
                <form onSubmit={handleSubmit} style={{ marginTop: '24px' }}>
                    <div className="form-group">
                        <label>Manga Title</label>
                        <input
                            required
                            className="form-input"
                            value={formData.title}
                            onChange={e => setFormData({ ...formData, title: e.target.value })}
                            placeholder="e.g. Jujutsu Kaisen"
                        />
                    </div>
                    <div className="form-group">
                        <label>MangaDex ID</label>
                        <input
                            required
                            className="form-input"
                            value={formData.mangadex_id}
                            onChange={e => setFormData({ ...formData, mangadex_id: e.target.value })}
                            placeholder="UUID from mangadex.org"
                        />
                    </div>
                    <div className="flex-row">
                        <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn-primary" disabled={saving}>
                            {saving ? 'Adding...' : 'Add Manga'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

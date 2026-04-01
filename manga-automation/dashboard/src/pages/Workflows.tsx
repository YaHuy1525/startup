import { useState, useEffect } from "react";
import { RefreshCw, Clock, CheckCircle, XCircle, Loader } from "lucide-react";
import { API_BASE } from '../config';

interface WorkflowExecution {
    id: number;
    workflow_name: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    duration_ms: number | null;
}

export default function Workflows() {
    const [workflows, setWorkflows] = useState<WorkflowExecution[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchWorkflows = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/workflows?limit=20`);
            const data = await res.json();
            setWorkflows(data.workflows || []);
        } catch (error) {
            console.error('Failed to fetch workflows:', error);
        }
        setLoading(false);
    };

    useEffect(() => {
        fetchWorkflows();
    }, []);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed':
                return <CheckCircle size={20} color="var(--success)" />;
            case 'failed':
                return <XCircle size={20} color="var(--danger)" />;
            case 'running':
                return <Loader size={20} color="var(--accent-primary)" className="spin" />;
            default:
                return <Clock size={20} color="var(--text-secondary)" />;
        }
    };

    const formatDuration = (ms: number | null) => {
        if (!ms) return '-';
        const seconds = Math.floor(ms / 1000);
        if (seconds < 60) return `${seconds}s`;
        const minutes = Math.floor(seconds / 60);
        return `${minutes}m ${seconds % 60}s`;
    };

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now.getTime() - date.getTime();
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(diff / 3600000);
        const days = Math.floor(diff / 86400000);

        if (minutes < 60) return `${minutes}m ago`;
        if (hours < 24) return `${hours}h ago`;
        return `${days}d ago`;
    };

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title">n8n Workflows</h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
                        Manage and track your automated pipelines.
                    </p>
                </div>
                <button className="btn-secondary" onClick={fetchWorkflows}>
                    <RefreshCw size={18} className={loading ? "spin" : ""} />
                    Refresh
                </button>
            </div>

            {loading ? (
                <div className="loading-container" style={{ minHeight: '400px' }}>
                    <div className="loading-spinner"></div>
                    <p>Loading workflows...</p>
                </div>
            ) : workflows.length === 0 ? (
                <div className="glass" style={{ padding: '48px', textAlign: 'center' }}>
                    <p style={{ color: 'var(--text-secondary)' }}>No workflow executions found.</p>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px', fontSize: '14px' }}>
                        Workflows will appear here once they start running.
                    </p>
                </div>
            ) : (
                <div className="glass table-container">
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>Workflow</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Duration</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {workflows.map((wf) => (
                                <tr key={wf.id}>
                                    <td style={{ fontWeight: 500 }}>{wf.workflow_name}</td>
                                    <td>
                                        <span className={`badge ${wf.status}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', width: 'fit-content' }}>
                                            {getStatusIcon(wf.status)}
                                            {wf.status}
                                        </span>
                                    </td>
                                    <td>{formatDate(wf.started_at)}</td>
                                    <td>{formatDuration(wf.duration_ms)}</td>
                                    <td>
                                        <button 
                                            className="btn-secondary" 
                                            style={{ padding: '6px 12px', fontSize: '13px' }}
                                            onClick={() => window.location.href = `/workflows/${wf.id}`}
                                        >
                                            View Details
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </>
    );
}

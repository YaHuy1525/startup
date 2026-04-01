import { useState, useEffect } from "react";
import { Calendar as CalendarIcon } from "lucide-react";
import { API_BASE } from '../config';

interface ScheduledVideo {
    id: number;
    manga_title: string;
    chapter_number: string;
    scheduled_for: string;
    status: string;
}

export default function ContentCalendar() {
    const [videos, setVideos] = useState<ScheduledVideo[]>([]);
    const [loading, setLoading] = useState(true);
    const [currentDate] = useState(new Date());

    useEffect(() => {
        const fetchScheduledVideos = async () => {
            try {
                const res = await fetch(`${API_BASE}/dashboard/videos`);
                const data = await res.json();
                // Filter only scheduled videos
                const scheduled = data.videos?.filter((v: any) => v.scheduled_for) || [];
                setVideos(scheduled);
            } catch (error) {
                console.error('Failed to fetch scheduled videos:', error);
            }
            setLoading(false);
        };

        fetchScheduledVideos();
    }, []);

    const getDaysInMonth = () => {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        return { firstDay, daysInMonth };
    };

    const { firstDay, daysInMonth } = getDaysInMonth();
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    const getVideosForDay = (day: number) => {
        return videos.filter(v => {
            const videoDate = new Date(v.scheduled_for);
            return videoDate.getDate() === day && 
                   videoDate.getMonth() === currentDate.getMonth() &&
                   videoDate.getFullYear() === currentDate.getFullYear();
        });
    };

    return (
        <>
            <div className="header-container">
                <div>
                    <h2 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <CalendarIcon size={32} /> Content Calendar
                    </h2>
                    <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
                        Drag and drop manga chapters to schedule your TikTok uploads.
                    </p>
                </div>
            </div>

            {loading ? (
                <div className="loading-container" style={{ minHeight: '400px' }}>
                    <div className="loading-spinner"></div>
                    <p>Loading calendar...</p>
                </div>
            ) : (
                <div className="glass" style={{ padding: '24px' }}>
                    <div style={{ 
                        display: 'grid', 
                        gridTemplateColumns: 'repeat(7, 1fr)', 
                        gap: '8px',
                        marginBottom: '16px'
                    }}>
                        {days.map(day => (
                            <div key={day} style={{ 
                                fontWeight: 600, 
                                textAlign: 'center', 
                                color: 'var(--text-secondary)',
                                padding: '8px'
                            }}>
                                {day}
                            </div>
                        ))}
                    </div>

                    <div style={{ 
                        display: 'grid', 
                        gridTemplateColumns: 'repeat(7, 1fr)', 
                        gap: '8px'
                    }}>
                        {/* Empty cells for days before month starts */}
                        {Array.from({ length: firstDay }).map((_, i) => (
                            <div key={`empty-${i}`} style={{ minHeight: '100px' }} />
                        ))}

                        {/* Days of the month */}
                        {Array.from({ length: daysInMonth }).map((_, i) => {
                            const day = i + 1;
                            const dayVideos = getVideosForDay(day);
                            const isToday = day === new Date().getDate() && 
                                          currentDate.getMonth() === new Date().getMonth() &&
                                          currentDate.getFullYear() === new Date().getFullYear();

                            return (
                                <div 
                                    key={day} 
                                    style={{ 
                                        minHeight: '100px',
                                        background: isToday ? 'rgba(99, 102, 241, 0.1)' : 'rgba(0, 0, 0, 0.2)',
                                        border: isToday ? '2px solid var(--accent-primary)' : '1px solid var(--border-color)',
                                        borderRadius: '8px',
                                        padding: '8px',
                                        display: 'flex',
                                        flexDirection: 'column'
                                    }}
                                >
                                    <div style={{ 
                                        textAlign: 'right', 
                                        fontSize: '14px', 
                                        color: isToday ? 'var(--accent-primary)' : 'var(--text-secondary)',
                                        fontWeight: isToday ? 600 : 400,
                                        marginBottom: '4px'
                                    }}>
                                        {day}
                                    </div>
                                    {dayVideos.map(video => (
                                        <div 
                                            key={video.id} 
                                            style={{ 
                                                fontSize: '11px',
                                                padding: '4px 6px',
                                                marginTop: '4px',
                                                borderRadius: '4px',
                                                background: video.status === 'ready' ? 'var(--accent-primary)' : 'var(--warning)',
                                                color: 'white',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap'
                                            }}
                                            title={`${video.manga_title} Ch${video.chapter_number}`}
                                        >
                                            {video.manga_title} Ch{video.chapter_number}
                                        </div>
                                    ))}
                                </div>
                            );
                        })}
                    </div>

                    {videos.length === 0 && (
                        <div style={{ 
                            textAlign: 'center', 
                            padding: '48px', 
                            color: 'var(--text-secondary)' 
                        }}>
                            <p>No videos scheduled yet.</p>
                            <p style={{ fontSize: '14px', marginTop: '8px' }}>
                                Schedule videos to see them on the calendar.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </>
    );
}

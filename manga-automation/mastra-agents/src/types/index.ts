export interface TrendingManga {
    id: string;
    title: string;
    source: 'mangadex' | 'anilist' | 'db';
    score: number;
    tags: string[];
}

export interface PanelAnalysis {
    score: number;
    reasoning: string;
    emotion: 'epic' | 'sad' | 'funny' | 'shocking' | 'romantic' | 'neutral';
    hasDialogue: boolean;
    dialogueText?: string;
    recommended: boolean;
    motionType: 'zoom_center' | 'pan_right' | 'pan_up';
    audioMood: 'phonk' | 'melancholic_piano' | 'lofi' | 'intense_synth';
}

export interface SelectedPanel {
    panelIndex: number;
    url: string;
    localPath?: string;
    score: number;
    reasoning: string;
    emotion: string;
    dialogueText?: string;
    motionType?: string;
    audioMood?: string;
}

export interface VideoJob {
    chapterId: number;
    mangaTitle: string;
    chapterNumber: string;
    panelPaths: string[];
    outputPath: string;
}

export interface PublishJob {
    videoId: number;
    videoPath: string;
    thumbnailPath?: string;
    caption: string;
    hashtags: string[];
    platforms: Array<'tiktok' | 'instagram' | 'youtube'>;
}

export interface AnalyticsData {
    publishedVideoId: number;
    platform: string;
    views: number;
    likes: number;
    comments: number;
    shares: number;
}

// Re-export QueueManager types
export { QueueEntry, QueueStatus } from '../tools/queueManager';

// Re-export ChapterAnalyzer types
export { 
  Panel, 
  VideoSplitPlan, 
  VideoSegment, 
  VideoTemplate, 
  EffectsConfig 
} from '../tools/chapterAnalyzer';

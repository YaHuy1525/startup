import { db, logger } from './database';

// ─── Interfaces ──────────────────────────────────────────────────────────────

export interface Panel {
  index: number;
  imageUrl: string;
  text?: string;
  isSceneChange?: boolean;
  isDramaticMoment?: boolean;
}

export interface VideoSplitPlan {
  chapterId: number;
  totalPanels: number;
  videoCount: number;
  splits: VideoSegment[];
}

export interface VideoSegment {
  partNumber: number;
  startPanel: number;
  endPanel: number;
  estimatedDuration: number;
  splitReason: 'scene_change' | 'dramatic_moment' | 'panel_limit' | 'duration_limit';
}

export interface VideoTemplate {
  id: number;
  name: string;
  type: 'emotional_scene' | 'character_edit' | 'recommendation' | 'top_list' | 'panel_appreciation';
  panelDuration: number; // seconds per panel
  transitionType: 'crossfade' | 'slide' | 'zoom' | 'wipe';
  transitionDuration: number;
  effectsConfig: EffectsConfig;
}

export interface EffectsConfig {
  zoomIntensity: number; // 1.0 = no zoom, 1.2 = 20% zoom
  panDirection: 'random' | 'left-to-right' | 'top-to-bottom';
  colorGrading?: string;
  overlayEffects?: string[];
}

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * Buffer time for intro/outro content (title cards, transitions, etc.)
 * This ensures videos meet the 60-second minimum even with fewer panels
 */
const INTRO_OUTRO_BUFFER_SECONDS = 8;

// ─── ChapterAnalyzer Class ───────────────────────────────────────────────────

export class ChapterAnalyzer {
  /**
   * Analyze chapter and determine video split strategy
   * @param chapterId - The chapter ID to analyze
   * @returns Video split plan with segments
   */
  async analyzeChapter(chapterId: number): Promise<VideoSplitPlan> {
    try {
      logger.info(`Analyzing chapter ${chapterId}`);

      // Fetch chapter data from database
      const chapterResult = await db.query(
        `SELECT panel_urls, total_panels
         FROM manga_chapters
         WHERE id = $1`,
        [chapterId]
      );

      if (chapterResult.rows.length === 0) {
        throw new Error(`Chapter ${chapterId} not found`);
      }

      const { panel_urls, total_panels } = chapterResult.rows[0];
      
      // panel_urls is a JSONB array of image URLs
      const panelUrls: string[] = panel_urls || [];
      
      if (panelUrls.length === 0) {
        throw new Error(`No panels found for chapter ${chapterId}`);
      }

      // Convert panel URLs to Panel objects
      const panels: Panel[] = panelUrls.map((url: string, index: number) => ({
        index,
        imageUrl: url
      }));
      const totalPanels = panels.length;

      // Get default template for duration estimation
      const template = await this.getDefaultTemplate();
      
      // Find optimal split points
      const splitPoints = this.findSplitPoints(panels, 120); // Target 2 minutes (120 seconds)

      // Build video segments from split points
      const splits: VideoSegment[] = [];
      let currentStart = 0;

      for (let i = 0; i < splitPoints.length; i++) {
        const endPanel = splitPoints[i].panelIndex;
        const panelCount = endPanel - currentStart + 1;
        const estimatedDuration = this.estimateDuration(panelCount, template);

        splits.push({
          partNumber: i + 1,
          startPanel: currentStart,
          endPanel: endPanel,
          estimatedDuration,
          splitReason: splitPoints[i].reason
        });

        currentStart = endPanel + 1;
      }

      // Add final segment if there are remaining panels
      if (currentStart < totalPanels) {
        const panelCount = totalPanels - currentStart;
        const estimatedDuration = this.estimateDuration(panelCount, template);

        splits.push({
          partNumber: splits.length + 1,
          startPanel: currentStart,
          endPanel: totalPanels - 1,
          estimatedDuration,
          splitReason: 'panel_limit'
        });
      }

      const videoCount = splits.length;

      logger.info(`Chapter ${chapterId} analysis complete: ${totalPanels} panels, ${videoCount} videos`);

      return {
        chapterId,
        totalPanels,
        videoCount,
        splits
      };
    } catch (error) {
      logger.error(`Error analyzing chapter ${chapterId}`, { error });
      throw error;
    }
  }

  /**
   * Estimate video duration based on panel count and template
   * Includes intro/outro buffer and dynamically extends panel duration if needed
   * @param panelCount - Number of panels
   * @param template - Video template with timing configuration
   * @returns Estimated duration in seconds
   */
  estimateDuration(panelCount: number, template: VideoTemplate): number {
    // Base calculation: (panels * panelDuration) + (transitions * transitionDuration)
    const transitionCount = Math.max(0, panelCount - 1);
    const transitionTime = transitionCount * template.transitionDuration;
    
    // Calculate base panel time
    let panelDuration = template.panelDuration;
    let panelTime = panelCount * panelDuration;
    
    // Add intro/outro buffer
    const totalDuration = panelTime + transitionTime + INTRO_OUTRO_BUFFER_SECONDS;
    
    // If total duration is less than 60 seconds, extend panel duration to meet minimum
    const MIN_DURATION = 60;
    if (totalDuration < MIN_DURATION) {
      // Calculate required panel duration to reach minimum
      const requiredPanelTime = MIN_DURATION - transitionTime - INTRO_OUTRO_BUFFER_SECONDS;
      panelDuration = requiredPanelTime / panelCount;
      panelTime = panelCount * panelDuration;
      
      return Math.round(panelTime + transitionTime + INTRO_OUTRO_BUFFER_SECONDS);
    }
    
    return Math.round(totalDuration);
  }

  /**
   * Find optimal split points in chapter based on panel analysis
   * Accounts for intro/outro buffer when calculating panel limits
   * @param panels - Array of panels to analyze
   * @param targetDuration - Target duration in seconds for each video
   * @returns Array of split points with reasons
   */
  findSplitPoints(panels: Panel[], targetDuration: number): Array<{ panelIndex: number; reason: VideoSegment['splitReason'] }> {
    const splitPoints: Array<{ panelIndex: number; reason: VideoSegment['splitReason'] }> = [];
    
    // Get default template for duration calculations
    const defaultPanelDuration = 4; // seconds per panel (default)
    const defaultTransitionDuration = 0.5; // seconds per transition
    
    // Minimum panels per video (based on 1 minute minimum - Requirement 5A.4)
    // Account for intro/outro buffer: 60 seconds - 8 seconds buffer = 52 seconds for content
    const minContentDuration = 60 - INTRO_OUTRO_BUFFER_SECONDS;
    const minPanelsPerVideo = Math.ceil((minContentDuration - defaultTransitionDuration) / (defaultPanelDuration + defaultTransitionDuration));
    
    // Maximum panels per video (based on 3 minute limit)
    // Account for intro/outro buffer: 180 seconds - 8 seconds buffer = 172 seconds for content
    const maxContentDuration = 180 - INTRO_OUTRO_BUFFER_SECONDS;
    const maxPanelsPerVideo = Math.floor((maxContentDuration - defaultTransitionDuration) / (defaultPanelDuration + defaultTransitionDuration));
    
    // Target panels per video (based on target duration)
    // Account for intro/outro buffer
    const targetContentDuration = targetDuration - INTRO_OUTRO_BUFFER_SECONDS;
    const targetPanelsPerVideo = Math.floor((targetContentDuration - defaultTransitionDuration) / (defaultPanelDuration + defaultTransitionDuration));
    
    let currentSegmentStart = 0;
    let currentPanelCount = 0;

    for (let i = 0; i < panels.length; i++) {
      currentPanelCount++;
      const panel = panels[i];

      // Check if we've hit the maximum panel limit
      if (currentPanelCount >= maxPanelsPerVideo) {
        splitPoints.push({ panelIndex: i, reason: 'panel_limit' });
        currentSegmentStart = i + 1;
        currentPanelCount = 0;
        continue;
      }

      // Check if we've hit the target duration
      if (currentPanelCount >= targetPanelsPerVideo) {
        // Calculate remaining panels after this split
        const remainingPanels = panels.length - i - 1;
        
        // Only split if remaining panels meet minimum requirement
        if (remainingPanels >= minPanelsPerVideo) {
          // Look ahead for a good split point (scene change or dramatic moment)
          const lookAheadRange = Math.min(5, panels.length - i - 1);
          let bestSplitIndex = i;
          let bestSplitReason: VideoSegment['splitReason'] = 'duration_limit';

          for (let j = 0; j <= lookAheadRange; j++) {
            const lookAheadPanel = panels[i + j];
            
            if (lookAheadPanel.isSceneChange) {
              bestSplitIndex = i + j;
              bestSplitReason = 'scene_change';
              break;
            }
            
            if (lookAheadPanel.isDramaticMoment) {
              bestSplitIndex = i + j;
              bestSplitReason = 'dramatic_moment';
            }
          }

          // Verify the split still leaves enough panels for the next segment
          const remainingAfterSplit = panels.length - bestSplitIndex - 1;
          if (remainingAfterSplit >= minPanelsPerVideo && bestSplitIndex < panels.length - 1) {
            splitPoints.push({ panelIndex: bestSplitIndex, reason: bestSplitReason });
            currentSegmentStart = bestSplitIndex + 1;
            currentPanelCount = 0;
            i = bestSplitIndex; // Skip to the split point
          }
        }
      }
    }

    return splitPoints;
  }

  /**
   * Get default video template from database
   * @returns Default video template
   */
  private async getDefaultTemplate(): Promise<VideoTemplate> {
    try {
      const result = await db.query(
        `SELECT 
          id,
          name,
          type,
          panel_duration as "panelDuration",
          transition_type as "transitionType",
          transition_duration as "transitionDuration",
          effects_config as "effectsConfig"
         FROM video_templates
         ORDER BY usage_count DESC
         LIMIT 1`
      );

      if (result.rows.length === 0) {
        // Return hardcoded default if no templates in database
        return {
          id: 0,
          name: 'Default',
          type: 'emotional_scene',
          panelDuration: 4,
          transitionType: 'crossfade',
          transitionDuration: 0.5,
          effectsConfig: {
            zoomIntensity: 1.2,
            panDirection: 'random'
          }
        };
      }

      return result.rows[0];
    } catch (error) {
      logger.error('Error fetching default template', { error });
      // Return hardcoded default on error
      return {
        id: 0,
        name: 'Default',
        type: 'emotional_scene',
        panelDuration: 4,
        transitionType: 'crossfade',
        transitionDuration: 0.5,
        effectsConfig: {
          zoomIntensity: 1.2,
          panDirection: 'random'
        }
      };
    }
  }
}

// Export singleton instance
export const chapterAnalyzer = new ChapterAnalyzer();

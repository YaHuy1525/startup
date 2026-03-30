import { db, logger } from './database';

// ─── Interfaces ──────────────────────────────────────────────────────────────

export enum FormulaType {
  EMOTIONAL_HOOK = 'emotional_hook',
  QUESTION = 'question',
  RELATABLE = 'relatable',
  RECOMMENDATION = 'recommendation',
  STATEMENT_EMOJI = 'statement_emoji'
}

export interface CaptionFormula {
  id: number;
  formula_type: FormulaType;
  template: string;
  emoji_suggestions: string[];
}

export interface Caption {
  text: string;
  formula: FormulaType;
  emojis: string[];
}

export interface CaptionRequest {
  mangaTitle: string;
  chapterNumber: string;
  genre: string;
  emotionalTone?: 'sad' | 'exciting' | 'funny' | 'intense';
  formulaType?: FormulaType;
}

// ─── CaptionGenerator Class ──────────────────────────────────────────────────

export class CaptionGenerator {
  /**
   * Generate caption for video
   * @param request - Caption generation request
   * @returns Generated caption with formula and emojis
   */
  async generateCaption(request: CaptionRequest): Promise<Caption> {
    try {
      logger.info(`Generating caption for ${request.mangaTitle} chapter ${request.chapterNumber}`);

      // Get formula (either specified or random)
      const formula = request.formulaType
        ? await this.getFormulaByType(request.formulaType)
        : await this.getRandomFormula();

      // Replace template variables
      let captionText = formula.template
        .replace(/{manga}/g, request.mangaTitle || 'this manga')
        .replace(/{chapter}/g, request.chapterNumber || '')
        .replace(/{genre}/g, request.genre || '')
        .replace(/{emotion}/g, request.emotionalTone || '');

      // Select 1-3 emojis from suggestions
      const selectedEmojis = this.selectEmojis(formula.emoji_suggestions);

      // Insert emojis into caption
      captionText = this.insertEmojis(captionText, selectedEmojis);

      logger.info(`Generated caption: ${captionText}`);

      return {
        text: captionText,
        formula: formula.formula_type,
        emojis: selectedEmojis
      };
    } catch (error) {
      logger.error('Error generating caption', { error, request });
      throw error;
    }
  }

  /**
   * Get random formula from database
   * @returns Random caption formula
   */
  async getRandomFormula(): Promise<CaptionFormula> {
    try {
      const result = await db.query(
        `SELECT * FROM caption_templates 
         ORDER BY RANDOM() 
         LIMIT 1`
      );

      if (result.rows.length === 0) {
        throw new Error('No caption templates found in database');
      }

      return result.rows[0];
    } catch (error) {
      logger.error('Error getting random formula', { error });
      throw error;
    }
  }

  /**
   * Get formula by type
   * @param type - Formula type to retrieve
   * @returns Caption formula of specified type
   */
  async getFormulaByType(type: FormulaType): Promise<CaptionFormula> {
    try {
      const result = await db.query(
        `SELECT * FROM caption_templates 
         WHERE formula_type = $1 
         ORDER BY RANDOM() 
         LIMIT 1`,
        [type]
      );

      if (result.rows.length === 0) {
        logger.warn(`No formula found for type ${type}, falling back to random`);
        return this.getRandomFormula();
      }

      return result.rows[0];
    } catch (error) {
      logger.error('Error getting formula by type', { error, type });
      throw error;
    }
  }

  /**
   * Select 1-3 emojis from suggestions
   * @param suggestions - Array of emoji suggestions
   * @returns Array of 1-3 selected emojis
   */
  private selectEmojis(suggestions: string[]): string[] {
    if (!suggestions || suggestions.length === 0) {
      // Default emojis if none provided
      return ['📚'];
    }

    // Randomly select 1-3 emojis
    const count = Math.floor(Math.random() * 3) + 1; // 1, 2, or 3
    const shuffled = [...suggestions].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, Math.min(count, suggestions.length));
  }

  /**
   * Insert emojis appropriately in caption text
   * @param text - Caption text
   * @param emojis - Array of emojis to insert
   * @returns Caption text with emojis inserted
   */
  private insertEmojis(text: string, emojis: string[]): string {
    // Check if template already has {emoji} placeholder
    if (text.includes('{emoji}')) {
      return text.replace(/{emoji}/g, emojis.join(' '));
    }

    // Otherwise, append emojis at the end
    return `${text} ${emojis.join(' ')}`;
  }
}

// Export singleton instance
export const captionGenerator = new CaptionGenerator();

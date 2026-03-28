#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# generate_manga_video.sh
# Converts 3-5 manga panel images into a 9:16 vertical video with:
#   - Ken Burns zoom/pan effect on each panel
#   - Cross-fade transitions between panels
#   - Optional background music
#   - Optional caption overlay
# ─────────────────────────────────────────────────────────────────────────────
#
# Usage:
#   ./generate_manga_video.sh \
#     --panels "/data/panels/one_piece/ch_1000/panel_001.jpg,/data/panels/.../panel_002.jpg" \
#     --output "/data/videos/op_ch1000_20260310.mp4" \
#     --music  "/data/music/dramatic_01.mp3" \
#     --title  "One Piece" \
#     --chapter "Chapter 1000"

set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
PANELS=""
OUTPUT=""
MUSIC=""
TITLE=""
CHAPTER=""
PANEL_DURATION=4     # seconds per panel
TRANSITION_DURATION=0.5
WIDTH=1080
HEIGHT=1920
FPS=30
TMP_DIR=$(mktemp -d)

# ─── Arg parse ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --panels)   PANELS="$2";   shift 2 ;;
    --output)   OUTPUT="$2";   shift 2 ;;
    --music)    MUSIC="$2";    shift 2 ;;
    --title)    TITLE="$2";    shift 2 ;;
    --chapter)  CHAPTER="$2";  shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$PANELS" || -z "$OUTPUT" ]]; then
  echo "Error: --panels and --output are required"
  exit 1
fi

IFS=',' read -ra PANEL_ARRAY <<< "$PANELS"
PANEL_COUNT=${#PANEL_ARRAY[@]}

echo "🎬 Generating manga video"
echo "   Panels: $PANEL_COUNT | Output: $OUTPUT"

# ─── Step 1: Apply Ken Burns effect to each panel ─────────────────────────────
ZOOMED_FILES=()
for i in "${!PANEL_ARRAY[@]}"; do
  PANEL="${PANEL_ARRAY[$i]}"
  ZOOMED="$TMP_DIR/panel_${i}_zoomed.mp4"

  # Alternate between zoom-in and pan-right for variety
  if (( i % 2 == 0 )); then
    # Zoom in from center
    ZOOM_EXPR="zoom='min(zoom+0.0015,1.5)':d=$((PANEL_DURATION * FPS)):x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
  else
    # Pan left to right
    ZOOM_EXPR="zoom=1.2:d=$((PANEL_DURATION * FPS)):x='if(gte(on,1),if(lte(iw/zoom/2+on*2,iw),iw/zoom/2+on*2,iw-iw/zoom/2),iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
  fi

  ffmpeg -y -loop 1 -i "$PANEL" \
    -vf "scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=increase,\
         crop=${WIDTH}:${HEIGHT},\
         zoompan=${ZOOM_EXPR}:s=${WIDTH}x${HEIGHT},\
         format=yuv420p" \
    -t "$PANEL_DURATION" -r "$FPS" \
    -c:v libx264 -preset fast -crf 22 \
    "$ZOOMED" -loglevel error

  ZOOMED_FILES+=("$ZOOMED")
  echo "   ✓ Panel $((i+1))/$PANEL_COUNT processed"
done

# ─── Step 2: Concatenate with crossfade transitions ──────────────────────────
FILTER_COMPLEX=""
PREV_LABEL="[0:v]"
OFFSET=$(echo "$PANEL_DURATION - $TRANSITION_DURATION" | bc)

for i in "${!ZOOMED_FILES[@]}"; do
  if (( i < PANEL_COUNT - 1 )); then
    NEXT_IDX=$((i + 1))
    OUT_LABEL="[v${i}${NEXT_IDX}]"
    FILTER_COMPLEX+="${PREV_LABEL}[$((i+1)):v]xfade=transition=fadeblack:duration=${TRANSITION_DURATION}:offset=${OFFSET}${OUT_LABEL};"
    OFFSET=$(echo "$OFFSET + $PANEL_DURATION - $TRANSITION_DURATION" | bc)
    PREV_LABEL="$OUT_LABEL"
  fi
done

# Build ffmpeg input args
INPUT_ARGS=()
for f in "${ZOOMED_FILES[@]}"; do
  INPUT_ARGS+=(-i "$f")
done

VIDEO_ONLY="$TMP_DIR/video_no_audio.mp4"

if (( PANEL_COUNT == 1 )); then
  # Single panel - just copy
  ffmpeg -y -i "${ZOOMED_FILES[0]}" -c copy "$VIDEO_ONLY" -loglevel error
else
  FILTER_COMPLEX="${FILTER_COMPLEX%;}";  # remove trailing semicolon
  FINAL_MAP="${PREV_LABEL}"

  ffmpeg -y "${INPUT_ARGS[@]}" \
    -filter_complex "$FILTER_COMPLEX" \
    -map "$FINAL_MAP" \
    -c:v libx264 -preset fast -crf 22 \
    "$VIDEO_ONLY" -loglevel error
fi

echo "   ✓ Panels concatenated with transitions"

# ─── Step 3: Add title card overlay ──────────────────────────────────────────
if [[ -n "$TITLE" ]]; then
  TITLE_VIDEO="$TMP_DIR/with_title.mp4"
  SAFE_TITLE=$(echo "$TITLE" | sed "s/'/\\\'/g")
  SAFE_CHAPTER=$(echo "$CHAPTER" | sed "s/'/\\\'/g")

  ffmpeg -y -i "$VIDEO_ONLY" \
    -vf "drawtext=fontfile=/usr/share/fonts/truetype/freefont/FreeSansBold.ttf:\
text='${SAFE_TITLE}':fontcolor=white:fontsize=52:x=(w-text_w)/2:y=80:\
shadowcolor=black:shadowx=3:shadowy=3:enable='between(t,0,3)',\
drawtext=fontfile=/usr/share/fonts/truetype/freefont/FreeSans.ttf:\
text='${SAFE_CHAPTER}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=150:\
shadowcolor=black:shadowx=2:shadowy=2:enable='between(t,0,3)'" \
    -c:v libx264 -preset fast -crf 22 -c:a copy \
    "$TITLE_VIDEO" -loglevel error

  mv "$TITLE_VIDEO" "$VIDEO_ONLY"
  echo "   ✓ Title overlay added"
fi

# ─── Step 4: Mix in background music ─────────────────────────────────────────
if [[ -n "$MUSIC" && -f "$MUSIC" ]]; then
  ffmpeg -y -i "$VIDEO_ONLY" -i "$MUSIC" \
    -filter_complex "[1:a]volume=0.4,afade=t=out:st=$(echo "$PANEL_COUNT * $PANEL_DURATION - 2" | bc):d=2[music];[music]" \
    -map 0:v -map "[music]" \
    -c:v copy -c:a aac -b:a 128k -shortest \
    "$OUTPUT" -loglevel error
  echo "   ✓ Music mixed in"
else
  # No music - just copy the silent video
  cp "$VIDEO_ONLY" "$OUTPUT"
fi

# ─── Cleanup ─────────────────────────────────────────────────────────────────
rm -rf "$TMP_DIR"

FILE_SIZE=$(du -sh "$OUTPUT" | cut -f1)
echo "✅ Video created: $OUTPUT ($FILE_SIZE)"

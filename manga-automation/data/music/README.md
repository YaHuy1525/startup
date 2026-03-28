# Background Music for Manga Videos

The `musicSelector` agent automatically picks a track from one of the folders
below based on the dominant emotion detected in the selected manga panels.

## Folder structure

```
data/music/
  epic/       ← action, power-ups, boss fights, intense moments
  sad/        ← death, betrayal, emotional breakdowns
  funny/      ← comedy, chibi scenes, gag moments
  shocking/   ← plot twists, unexpected reveals
  romantic/   ← love confessions, tender moments
  neutral/    ← fallback for any other mood
```

## Supported formats

`.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, `.aac`

## Where to get free music

All sources below allow royalty-free use in monetised short-form videos:

| Source | Notes |
|--------|-------|
| [Pixabay Music](https://pixabay.com/music/) | No attribution required |
| [Free Music Archive](https://freemusicarchive.org/) | Check individual licences |
| [Uppbeat](https://uppbeat.io/) | Free tier, attribution may be required |
| [Mixkit](https://mixkit.co/free-stock-music/) | No attribution required |
| [YouTube Audio Library](https://www.youtube.com/audiolibrary) | Free for YouTube; check TikTok ToS |

## Tips

- Keep tracks **60–120 seconds** so they loop cleanly over a 60 s video.
- Prefer **instrumental-only** tracks — vocals compete with on-screen text.
- Normalise loudness to **-14 LUFS** so FFmpeg doesn't need to adjust levels.
- The agent picks a **random** track from the matching folder every time,
  giving natural variety across videos.

## Override the music directory

Set the environment variable `MUSIC_DIR` in `manga-automation/.env` if you
store your music elsewhere:

```
MUSIC_DIR=/absolute/path/to/your/music
```

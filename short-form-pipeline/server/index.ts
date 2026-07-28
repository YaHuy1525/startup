/**
 * Express render server for the short-form pipeline.
 *
 * Endpoints:
 *   GET  /health                 -> { ok: true }
 *   GET  /compositions           -> list available compositions
 *   POST /render                 -> render a composition to MP4
 *        body: {
 *          id?: string,           // composition id (default: SHORT_COMP_ID or "ShortVideo")
 *          inputProps?: object,   // props passed to the composition
 *          filename?: string,     // output file name (default: video.mp4)
 *          download?: boolean      // stream the file back (default: false -> returns JSON + URL)
 *        }
 *
 * Rendered files are written to /out and served statically at /out/<file>.
 */
import path from "path";
import fs from "fs";
import express, { type Request, type Response } from "express";
import cors from "cors";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { enableTailwind } from "@remotion/tailwind-v4";

const PROJECT_ROOT = path.resolve(__dirname, "..");
const ENTRY_POINT = path.join(PROJECT_ROOT, "src", "index.ts");
const OUT_DIR = path.join(PROJECT_ROOT, "out");
const PORT = Number(process.env.PORT || 3333);
const DEFAULT_COMP = process.env.SHORT_COMP_ID || "ShortVideo";

fs.mkdirSync(OUT_DIR, { recursive: true });

const app = express();
app.use(cors());
app.use(express.json({ limit: "10mb" }));
app.use("/out", express.static(OUT_DIR));

/** Bundle once and reuse across renders (rebuild only on first request). */
let bundlePromise: Promise<string> | null = null;
function getBundle(): Promise<string> {
  if (!bundlePromise) {
    bundlePromise = bundle({
      entryPoint: ENTRY_POINT,
      // Compositions use TailwindCSS, so the render bundle needs it too.
      webpackOverride: (config) => enableTailwind(config),
    });
  }
  return bundlePromise;
}

app.get("/health", (_req: Request, res: Response) => {
  res.json({ ok: true, service: "short-form-render-server" });
});

app.get("/compositions", async (_req: Request, res: Response) => {
  try {
    const serveUrl = await getBundle();
    // selectComposition needs an id; list via the internal compositions API instead.
    const { getCompositions } = await import("@remotion/renderer");
    const comps = await getCompositions(serveUrl);
    res.json({
      compositions: comps.map((c) => ({
        id: c.id,
        width: c.width,
        height: c.height,
        fps: c.fps,
        durationInFrames: c.durationInFrames,
      })),
    });
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

app.post("/render", async (req: Request, res: Response) => {
  const {
    id = DEFAULT_COMP,
    inputProps = {},
    filename = "video.mp4",
    download = false,
  } = req.body || {};

  const safeName = String(filename).replace(/[^a-zA-Z0-9._-]/g, "_");
  const outputLocation = path.join(OUT_DIR, safeName);

  try {
    const serveUrl = await getBundle();
    const composition = await selectComposition({
      serveUrl,
      id,
      inputProps,
    });

    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation,
      inputProps,
    });

    // Remotion runs as root; python-worker is uid 1000 and must overwrite/compress.
    try {
      fs.chmodSync(outputLocation, 0o666);
    } catch {
      /* best-effort on Windows bind mounts */
    }

    if (download) {
      return res.download(outputLocation, safeName);
    }
    return res.json({
      success: true,
      id,
      file: outputLocation,
      url: `/out/${safeName}`,
      durationInFrames: composition.durationInFrames,
      dimensions: `${composition.width}x${composition.height}`,
    });
  } catch (err) {
    return res.status(500).json({ success: false, error: (err as Error).message });
  }
});

app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`Render server on http://localhost:${PORT} (default comp: ${DEFAULT_COMP})`);
});

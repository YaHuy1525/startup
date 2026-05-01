#!/usr/bin/env node
/**
 * Local Kokoro JS runner.
 *
 * Usage:
 *   node scripts/kokoro_tts_runner.mjs --text "hello" --output /tmp/out.wav --voice af_sky --dtype q8
 */
import fs from "fs";

const args = process.argv.slice(2);
const getArg = (name, fallback = "") => {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1 || idx === args.length - 1) return fallback;
  return args[idx + 1];
};

const text = getArg("text");
const output = getArg("output");
const voice = getArg("voice", "af_sky");
const dtype = getArg("dtype", "q8");
const model = getArg("model", "onnx-community/Kokoro-82M-v1.0-ONNX");

if (!text || !output) {
  console.error("Missing required args: --text and --output");
  process.exit(1);
}

try {
  const { KokoroTTS } = await import("kokoro-js");
  const tts = await KokoroTTS.from_pretrained(model, { dtype });
  const audio = await tts.generate(text, { voice });
  const wavBuffer = audio.toWav();
  fs.writeFileSync(output, Buffer.from(wavBuffer));
  process.stdout.write(
    JSON.stringify({ success: true, output, voice, provider: "kokoro-js" }),
  );
} catch (err) {
  process.stderr.write(
    JSON.stringify({
      success: false,
      error: String(err?.message || err),
      hint: "Install kokoro-js in container/app: npm i kokoro-js",
    }),
  );
  process.exit(2);
}

/**
 * Transcribe a voiceover audio file into TikTok-style captions using Whisper.cpp.
 *
 * Usage:
 *   npx tsx scripts/transcribe.ts <input-audio> [output-name] [model]
 *   npx tsx scripts/transcribe.ts public/voiceover.mp3 captions.json medium.en
 *
 * Output: writes captions JSON (Caption[]) into public/<output-name> so the
 * Remotion <Captions> component can fetch it via staticFile().
 */
import path from "path";
import fs from "fs";
import { execSync } from "child_process";
import {
  downloadWhisperModel,
  installWhisperCpp,
  transcribe,
  toCaptions,
  type WhisperModel,
} from "@remotion/install-whisper-cpp";

const WHISPER_VERSION = "1.5.5";

async function main() {
  const input = process.argv[2];
  const outName = process.argv[3] || "captions.json";
  const model = (process.argv[4] || "medium.en") as WhisperModel;

  if (!input) {
    console.error("Usage: npx tsx scripts/transcribe.ts <input-audio> [output.json] [model]");
    process.exit(1);
  }

  const projectRoot = process.cwd();
  const whisperDir = path.join(projectRoot, "whisper.cpp");
  const publicDir = path.join(projectRoot, "public");
  fs.mkdirSync(publicDir, { recursive: true });

  console.log(`Installing whisper.cpp v${WHISPER_VERSION}...`);
  await installWhisperCpp({ to: whisperDir, version: WHISPER_VERSION });

  console.log(`Downloading model ${model}...`);
  await downloadWhisperModel({ model, folder: whisperDir });

  // Whisper needs a 16KHz mono wav. Convert whatever we were given.
  const wavPath = path.join(publicDir, "_transcribe_input.wav");
  console.log("Converting audio to 16kHz wav (ffmpeg)...");
  execSync(`ffmpeg -i "${path.resolve(input)}" -ar 16000 -ac 1 "${wavPath}" -y`, {
    stdio: "inherit",
  });

  console.log("Transcribing...");
  const whisperCppOutput = await transcribe({
    model,
    whisperPath: whisperDir,
    whisperCppVersion: WHISPER_VERSION,
    inputPath: wavPath,
    tokenLevelTimestamps: true,
  });

  const { captions } = toCaptions({ whisperCppOutput });
  const outPath = path.join(publicDir, outName);
  fs.writeFileSync(outPath, JSON.stringify(captions, null, 2));
  fs.rmSync(wavPath, { force: true });

  console.log(`Wrote ${captions.length} captions -> ${outPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

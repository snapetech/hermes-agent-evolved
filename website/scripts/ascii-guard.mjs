#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const [, , command, target = "docs"] = process.argv;

if (command !== "lint") {
  console.error("Usage: node scripts/ascii-guard.mjs lint <dir>");
  process.exit(2);
}

const root = path.resolve(process.cwd(), target);
const markdownExts = new Set([".md", ".mdx"]);
const offenders = [];

function walk(dir) {
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
    } else if (markdownExts.has(path.extname(entry.name))) {
      lintFile(full);
    }
  }
}

function lintFile(file) {
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
  let inFence = false;
  let fenceLang = "";
  let fenceStart = 0;
  let fenceLines = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fence = line.match(/^```\s*([A-Za-z0-9_-]*)/);
    if (fence) {
      if (!inFence) {
        inFence = true;
        fenceLang = fence[1] || "";
        fenceStart = index + 1;
        fenceLines = [];
      } else {
        checkFence(file, fenceStart, fenceLang, fenceLines);
        inFence = false;
        fenceLang = "";
        fenceLines = [];
      }
      continue;
    }
    if (inFence) {
      fenceLines.push(line);
    }
  }
}

function checkFence(file, startLine, lang, lines) {
  if (["mermaid", "bash", "sh", "shell", "text", "json", "yaml", "python", "ts", "tsx", "js", "jsx"].includes(lang)) {
    return;
  }

  const hasAsciiBox = lines.some((line) => /^\s*\+[-=]{3,}\+/.test(line))
    || lines.filter((line) => /^\s*\|.*\|\s*$/.test(line)).length >= 3;

  if (hasAsciiBox) {
    offenders.push(`${path.relative(process.cwd(), file)}:${startLine}`);
  }
}

if (!fs.existsSync(root)) {
  console.error(`ascii-guard: target not found: ${target}`);
  process.exit(2);
}

walk(root);

if (offenders.length > 0) {
  console.error("ASCII box diagrams found. Use Mermaid, tables, or prose instead:");
  for (const offender of offenders) {
    console.error(`- ${offender}`);
  }
  process.exit(1);
}

console.log("ascii-guard: no ASCII box diagrams found");

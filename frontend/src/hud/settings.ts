import type { CSSProperties } from "react";

/**
 * The live view's URL settings. HANDOFF.md lists the tag and glass tints and the accent as
 * adjustable: /live?tag=0.6&glass=0.3&accent=cyan&boxes=0&mirror=1, or ?demo=1 for visual QA.
 */
export interface HudSettings {
  /** The mockup's scene and sample data; no camera, no socket. */
  demo: boolean;
  /** Mirror the camera feed and its boxes, like a selfie view. */
  mirror: boolean;
  /** Face box corner brackets. */
  boxes: boolean;
  /** Overrides of --hud-tag-bg, --hud-glass-bg and --hud-accent, for the stage element. */
  vars: CSSProperties;
}

const ACCENTS: Record<string, string> = {
  yellow: "#FFD84D",
  cyan: "#7FDBFF",
  green: "#9EF0B4",
  white: "#FFFFFF",
};

function isOn(value: string | null): boolean {
  return value !== null && /^(1|true|on|yes)$/i.test(value.trim());
}

function isOff(value: string | null): boolean {
  return value !== null && /^(0|false|off|no)$/i.test(value.trim());
}

function alpha(value: string | null, min: number, max: number): number | null {
  if (value === null || value.trim() === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : null;
}

/** A named alternate from the handoff, or a hex color with or without its "#". */
function accent(value: string | null): string | null {
  const v = value?.trim().toLowerCase();
  if (!v) return null;
  if (Object.hasOwn(ACCENTS, v)) return ACCENTS[v];
  const hex = v.replace(/^#/, "");
  return /^([0-9a-f]{3}|[0-9a-f]{6})$/.test(hex) ? `#${hex}` : null;
}

export function parseSettings(search: string): HudSettings {
  const params = new URLSearchParams(search);
  const vars: Record<string, string> = {};
  // Same base colors as the tokens in tokens.css; only the alpha is adjustable.
  const tag = alpha(params.get("tag"), 0.2, 0.85);
  if (tag !== null) vars["--hud-tag-bg"] = `rgba(0, 0, 0, ${tag})`;
  const glass = alpha(params.get("glass"), 0.1, 0.85);
  if (glass !== null) vars["--hud-glass-bg"] = `rgba(18, 20, 26, ${glass})`;
  const color = accent(params.get("accent"));
  if (color) vars["--hud-accent"] = color;
  return {
    demo: isOn(params.get("demo")),
    mirror: isOn(params.get("mirror")),
    boxes: !isOff(params.get("boxes")),
    vars: vars as CSSProperties,
  };
}

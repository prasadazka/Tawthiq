/**
 * Brand-name patches for the landing page.
 *
 * The landing visual is a single Figma SVG export in which every piece of
 * text was flattened to vector outlines (576 <path> elements, zero <text>).
 * The old product name is therefore *geometry*, not a string, and cannot be
 * find-and-replaced in the asset.
 *
 * So for each place the old name appeared we paint over the original block
 * with its sampled background colour and re-typeset the text as real HTML in
 * the same font / size / weight / colour that Figma used (per css.txt).
 *
 * Coordinates are in the native 1920x8090 Figma artboard space. Positions are
 * emitted as percentages and every length (font-size, line-height, radius,
 * padding) in `cqw` units, so the whole layer scales in lockstep with the
 * SVG at any viewport width.
 *
 * NOTE: the real fix is to change the text in Figma and re-export the SVG.
 * This layer exists because the Figma source file wasn't available. If the
 * SVG is ever re-exported, delete this file and the <BrandPatches/> call.
 */
import type { CSSProperties, ReactNode } from "react";

const PAGE_W = 1920;
const PAGE_H = 8090;

/** Artboard px -> container-query width units, so text scales with the SVG. */
const cq = (px: number) => `${((px / PAGE_W) * 100).toFixed(4)}cqw`;
const pctL = (px: number) => `${(px / PAGE_W) * 100}%`;
const pctT = (px: number) => `${(px / PAGE_H) * 100}%`;
const pctW = (px: number) => `${(px / PAGE_W) * 100}%`;
const pctH = (px: number) => `${(px / PAGE_H) * 100}%`;

interface Patch {
  /** Rect to repaint, in 1920x8090 artboard px. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Sampled fill of whatever sits behind the original text. */
  bg: string;
  font: string;
  size: number;
  weight: number;
  color: string;
  /** Line box height; defaults to `size` for single-line blocks. */
  lh?: number;
  align?: "left" | "center";
  /** Vertical placement inside the rect. */
  valign?: "top" | "center";
  radius?: number;
  border?: string;
  letterSpacing?: number;
  content: ReactNode;
}

/** Pencil-on-document glyph that precedes the CTA label in the original. */
function EditIcon() {
  return (
    <svg
      className="lp-patch-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14.5 3H5.5A2.5 2.5 0 0 0 3 5.5v13A2.5 2.5 0 0 0 5.5 21h13a2.5 2.5 0 0 0 2.5-2.5V10" />
      <path d="M17.6 2.6a2.1 2.1 0 0 1 3 3L12.4 13.8l-4 1 1-4Z" />
    </svg>
  );
}

/*
 * Every occurrence of the old name, with the geometry and type styles taken
 * from css.txt and the background colours sampled from a 1920x8090 render.
 *
 * Several rects are deliberately wider than the original: "Audit Siddhi" is
 * roughly 70% wider than the old name, so pills and buttons are repainted at
 * a larger width (kept centred on their original centre line) rather than
 * letting the longer label overflow the artwork.
 */
const PATCHES: Patch[] = [
  // 1. Header wordmark. css.txt L441: Geologica 700 24/30, #000, x=196 y=35.
  //    The money-stack icon to its left is left untouched.
  {
    x: 194, y: 33, w: 190, h: 34,
    bg: "#FFFFFF",
    font: "Geologica", size: 24, weight: 700, color: "#000000",
    align: "left", valign: "center",
    content: "Audit Siddhi",
  },

  // 2. Header CTA button. css.txt L724: Manrope 400 20/27, #FFF on #00653E.
  //    Original rect 1584,30 186x46 -> widened leftwards to fit the label;
  //    right edge held at 1770 (the 150px artboard gutter).
  {
    x: 1518, y: 30, w: 252, h: 46,
    bg: "#00653E", radius: 6,
    font: "Manrope", size: 20, weight: 400, color: "#FFFFFF",
    align: "center", valign: "center",
    content: "Audit Siddhi Tool",
  },

  // 3. Hero secondary button. css.txt L391: Manrope 600 20/27, #292929 on #D2D2D2.
  //    Original 361,720 190x52 -> widened rightwards into empty space.
  {
    x: 361, y: 720, w: 248, h: 52,
    bg: "#D2D2D2", radius: 6,
    font: "Manrope", size: 20, weight: 600, color: "#292929",
    align: "center", valign: "center",
    content: "Audit Siddhi Tool",
  },

  // 4. Section badge. css.txt L1533: Manrope 600 16/28 centred, #000.
  //    Pill outline is part of the SVG, so the pill is repainted too.
  {
    x: 115, y: 1983, w: 316, h: 48,
    bg: "#FDFFFF", radius: 22, border: "1px solid #000000",
    font: "Manrope", size: 16, weight: 600, color: "#000000",
    align: "center", valign: "center",
    content: "What Makes Audit Siddhi Different",
  },

  // 5. Body copy. css.txt L1171: Manrope 400 28/38, #000, 794px column @ 112,2215.
  {
    x: 110, y: 2208, w: 800, h: 170,
    bg: "#FDFFFF",
    font: "Manrope", size: 28, weight: 400, color: "#000000", lh: 38,
    align: "left", valign: "top",
    content:
      "Audit Siddhi transforms complex financial reporting into a streamlined, automated process. From validation to XBRL generation, every step is designed to reduce compliance risk, improve accuracy, and accelerate regulatory submissions.",
  },

  // 6. Body copy. css.txt L1189: Manrope 400 28/40, #000, 822px column @ 1022,3116.
  //    Sits on the light grey band (#F7F7F7).
  {
    x: 1020, y: 3108, w: 828, h: 216,
    bg: "#F7F7F7",
    font: "Manrope", size: 28, weight: 400, color: "#000000", lh: 40,
    align: "left", valign: "top",
    content:
      "Whether you're an audit firm, listed company, bank, or regulator, Audit Siddhi delivers the precision and control required for today's evolving compliance landscape. Automate repetitive reviews, enforce regulatory standards, and maintain confidence in every submission.",
  },

  // 7. Section badge. css.txt L1665: Manrope 600 16/28 centred, #000.
  //    Original pill ~808,4132 309x40 -> widened, held on the 960 centre line.
  {
    x: 786, y: 4130, w: 348, h: 44,
    bg: "#FDFFFF", radius: 22, border: "1px solid #000000",
    font: "Manrope", size: 16, weight: 600, color: "#000000",
    align: "center", valign: "center",
    content: "Why Organizations Choose Audit Siddhi",
  },

  // 8. Comparison heading. css.txt L1893: Manrope 700 56/76 centred.
  //    Two-tone in the artwork: the brand word is #00653E, the rest #0D200E.
  {
    x: 600, y: 5338, w: 720, h: 82,
    bg: "#FDFFFF",
    font: "Manrope", size: 56, weight: 700, color: "#0D200E", lh: 76,
    align: "center", valign: "center",
    content: (
      <>
        Why <span style={{ color: "#00653E" }}>Audit Siddhi</span> Wins?
      </>
    ),
  },

  // 9. Comparison table column header. css.txt L2038: Manrope 700 36/49, #000.
  //    Original 810,5499 139x49; kept centred at 879 between the adjacent columns.
  {
    x: 760, y: 5494, w: 240, h: 56,
    bg: "#FDFFFF",
    font: "Manrope", size: 36, weight: 700, color: "#000000",
    align: "center", valign: "center",
    content: "Audit Siddhi",
  },

  // 10. Closing CTA button. css.txt L3330: Figtree 600 20/24, #FFF on #00C77A.
  //     Original 809,7362 301x52 -> widened, held on the 960 centre line.
  {
    x: 780, y: 7362, w: 360, h: 52,
    bg: "#00C77A", radius: 6,
    font: "Figtree", size: 20, weight: 600, color: "#FFFFFF",
    align: "center", valign: "center",
    content: (
      <>
        <EditIcon />
        See Audit Siddhi in Action
      </>
    ),
  },

  // 11. Footer wordmark. css.txt L3563: Poppins 400 16/24, #040505 on #F7F9FC.
  {
    x: 114, y: 7818, w: 200, h: 28,
    bg: "#F7F9FC",
    font: "Poppins", size: 16, weight: 400, color: "#040505",
    align: "left", valign: "center",
    content: "Audit Siddhi",
  },
];

export default function LandingBrandPatches() {
  return (
    <>
      {PATCHES.map((p, i) => {
        const style: CSSProperties = {
          left: pctL(p.x),
          top: pctT(p.y),
          width: pctW(p.w),
          height: pctH(p.h),
          background: p.bg,
          color: p.color,
          fontFamily: `'${p.font}', system-ui, -apple-system, 'Segoe UI', sans-serif`,
          fontSize: cq(p.size),
          lineHeight: cq(p.lh ?? p.size),
          fontWeight: p.weight,
          justifyContent: p.align === "center" ? "center" : "flex-start",
          alignItems: p.valign === "top" ? "flex-start" : "center",
          textAlign: p.align === "center" ? "center" : "left",
        };
        if (p.radius) style.borderRadius = cq(p.radius);
        if (p.border) style.border = p.border;
        if (p.letterSpacing) style.letterSpacing = cq(p.letterSpacing);
        return (
          <div key={i} className="lp-patch" style={style}>
            <span className="lp-patch-text">{p.content}</span>
          </div>
        );
      })}
    </>
  );
}

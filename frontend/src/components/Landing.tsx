/**
 * Landing page for tawthiq.ai
 *
 * Renders the Figma export (svg.txt → /landing/landing-figma.svg) directly.
 * The SVG contains every vector path, gradient, filter, embedded image and
 * text glyph from the original design at 1920×8090, so the visual is
 * pixel-identical to Figma. On top, we overlay invisible clickable hotspots
 * at the exact button coordinates from css.txt so the page is interactive.
 */
import "../Landing.css";

interface Props {
  onLaunchTool: () => void;
}

// Figma artboard dimensions (css.txt line 4-5).
const PAGE_W = 1920;
const PAGE_H = 8090;

const pctL = (px: number) => `${(px / PAGE_W) * 100}%`;
const pctT = (px: number) => `${(px / PAGE_H) * 100}%`;
const pctW = (px: number) => `${(px / PAGE_W) * 100}%`;
const pctH = (px: number) => `${(px / PAGE_H) * 100}%`;

interface Hotspot {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  onClick?: () => void;
  href?: string;
}

export default function Landing({ onLaunchTool }: Props) {
  // Coordinates taken straight from css.txt:
  //
  //   Header "Tawthiq Tool" CTA  →  bar y:0 h:106, button 186×46, right-aligned
  //                                  with 150px padding → x=1584, y=30
  //   Hero "Book a Demo"         →  css.txt L287-364: 226×52 @ (117, 720)
  //   Hero "Tawthiq Tool" (gray) →  css.txt L371-410: 190×52 @ (361, 720)
  const hotspots: Hotspot[] = [
    { x: 1584, y: 30,  w: 186, h: 46, label: "Launch Tawthiq Tool",  onClick: onLaunchTool },
    { x: 117,  y: 720, w: 226, h: 52, label: "Book a Demo",          href: "mailto:hello@azkashine.com?subject=Tawthiq%20Demo%20Request" },
    { x: 361,  y: 720, w: 190, h: 52, label: "Launch Tawthiq Tool",  onClick: onLaunchTool },
  ];

  return (
    <div className="landing-page">
      <div className="lp-figma-stage">
        <img
          className="lp-figma-svg"
          src="/landing/landing-figma.svg"
          alt="Tawthiq — From Financial Statements to Regulatory Filing"
          loading="eager"
          decoding="async"
          draggable={false}
        />
        {hotspots.map((h, i) => {
          const style: React.CSSProperties = {
            position: "absolute",
            left: pctL(h.x),
            top: pctT(h.y),
            width: pctW(h.w),
            height: pctH(h.h),
          };
          if (h.onClick) {
            return (
              <button
                key={i}
                type="button"
                className="lp-hotspot"
                aria-label={h.label}
                style={style}
                onClick={h.onClick}
              />
            );
          }
          return (
            <a
              key={i}
              className="lp-hotspot"
              aria-label={h.label}
              href={h.href}
              style={style}
            />
          );
        })}
      </div>
    </div>
  );
}

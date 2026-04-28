import type { BoundingBox } from "../api";

interface Props {
  highlights: BoundingBox[];
  isFullPage: boolean;
}

export default function HighlightOverlay({ highlights, isFullPage }: Props) {
  if (!isFullPage && highlights.length === 0) return null;

  return (
    <div className="highlight-layer">
      {isFullPage ? (
        <div className="highlight-full-page" />
      ) : (
        highlights.map((box, i) => {
          const minX = Math.min(...box.vertices.map((v) => v.x));
          const minY = Math.min(...box.vertices.map((v) => v.y));
          const maxX = Math.max(...box.vertices.map((v) => v.x));
          const maxY = Math.max(...box.vertices.map((v) => v.y));

          return (
            <div
              key={i}
              className="highlight-box"
              style={{
                left: `${minX * 100}%`,
                top: `${minY * 100}%`,
                width: `${(maxX - minX) * 100}%`,
                height: `${(maxY - minY) * 100}%`,
              }}
            />
          );
        })
      )}
    </div>
  );
}

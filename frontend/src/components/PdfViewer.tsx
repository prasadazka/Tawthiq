import { useEffect, useRef, useState, useCallback } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import HighlightOverlay from "./HighlightOverlay";
import type { BoundingBox, RuleLocation } from "../api";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  url: string;
  currentPage: number;
  onPageChange: (page: number) => void;
  numPages: number;
  onNumPages: (n: number) => void;
  selectedLocations: RuleLocation[];
}

export default function PdfViewer({
  url,
  currentPage,
  onPageChange,
  numPages,
  onNumPages,
  selectedLocations,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [containerWidth, setContainerWidth] = useState(700);
  const [visiblePages, setVisiblePages] = useState<Set<number>>(new Set([1, 2, 3]));
  const scrollingToRef = useRef(false);
  const prevPageRef = useRef(currentPage);

  // Observe container width for responsive page rendering
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width - 48);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Page virtualization — only render pages near viewport
  useEffect(() => {
    if (numPages === 0) return;
    const observers = new Map<number, IntersectionObserver>();
    const root = containerRef.current;
    if (!root) return;

    const handleIntersect = (pageNum: number) => (entries: IntersectionObserverEntry[]) => {
      for (const entry of entries) {
        setVisiblePages((prev) => {
          const next = new Set(prev);
          if (entry.isIntersecting) {
            // Add this page and neighbors
            next.add(pageNum);
            if (pageNum > 1) next.add(pageNum - 1);
            if (pageNum < numPages) next.add(pageNum + 1);
          }
          return next;
        });

        // Track current page based on scroll position
        if (entry.isIntersecting && !scrollingToRef.current) {
          onPageChange(pageNum);
        }
      }
    };

    for (const [pageNum, el] of pageRefs.current) {
      const obs = new IntersectionObserver(handleIntersect(pageNum), {
        root,
        rootMargin: "200px 0px",
        threshold: 0.1,
      });
      obs.observe(el);
      observers.set(pageNum, obs);
    }

    return () => {
      for (const obs of observers.values()) obs.disconnect();
    };
  }, [numPages, onPageChange]);

  // Scroll to page when currentPage changes (triggered by rule click)
  const scrollToPage = useCallback(
    (page: number) => {
      const el = pageRefs.current.get(page);
      if (el) {
        scrollingToRef.current = true;
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        setTimeout(() => {
          scrollingToRef.current = false;
        }, 1000);
      }
    },
    []
  );

  // Scroll to page when currentPage changes from parent (rule click)
  useEffect(() => {
    if (currentPage !== prevPageRef.current && numPages > 0) {
      // Ensure the target page and its neighbors are visible (rendered)
      setVisiblePages((prev) => {
        const next = new Set(prev);
        next.add(currentPage);
        if (currentPage > 1) next.add(currentPage - 1);
        if (currentPage < numPages) next.add(currentPage + 1);
        return next;
      });
      // Small delay to let the page render before scrolling
      setTimeout(() => scrollToPage(currentPage), 100);
      prevPageRef.current = currentPage;
    }
  }, [currentPage, numPages, scrollToPage]);

  // Get highlights for a specific page
  const getHighlightsForPage = (pageNum: number): BoundingBox[] => {
    const loc = selectedLocations.find((l) => l.page === pageNum);
    if (!loc) return [];
    return loc.bounding_boxes;
  };

  const isFullPageHighlight = (pageNum: number): boolean => {
    const loc = selectedLocations.find((l) => l.page === pageNum);
    return loc !== undefined && loc.bounding_boxes.length === 0;
  };

  // Check if a page has any highlight
  const pageHasHighlight = (pageNum: number): boolean => {
    return selectedLocations.some((l) => l.page === pageNum);
  };

  return (
    <div className="pdf-viewer">
      {/* Toolbar */}
      <div className="pdf-toolbar">
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => {
            const p = Math.max(1, currentPage - 1);
            onPageChange(p);
            scrollToPage(p);
          }}
          disabled={currentPage <= 1}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span className="pdf-page-info">
          Page {currentPage} of {numPages}
        </span>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => {
            const p = Math.min(numPages, currentPage + 1);
            onPageChange(p);
            scrollToPage(p);
          }}
          disabled={currentPage >= numPages}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </div>

      {/* Scrollable pages */}
      <div className="pdf-scroll" ref={containerRef}>
        <Document
          file={url}
          onLoadSuccess={({ numPages: n }) => {
            onNumPages(n);
            setVisiblePages(new Set([1, 2, 3]));
          }}
          onLoadError={(error) => console.error("PDF load error:", error)}
          loading={<div className="pdf-loading">Loading PDF...</div>}
          error={<div className="pdf-loading">Failed to load PDF. Please try again.</div>}
        >
          {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNum) => (
            <div
              key={pageNum}
              ref={(el) => {
                if (el) pageRefs.current.set(pageNum, el);
              }}
              className={`pdf-page-wrap ${pageHasHighlight(pageNum) ? "pdf-page-highlighted" : ""}`}
            >
              <div className="pdf-page-num">Page {pageNum}</div>
              <div style={{ position: "relative" }}>
                {visiblePages.has(pageNum) ? (
                  <Page
                    pageNumber={pageNum}
                    width={containerWidth}
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                  />
                ) : (
                  <div
                    className="pdf-page-placeholder"
                    style={{ width: containerWidth, height: containerWidth * 1.414 }}
                  />
                )}
                <HighlightOverlay
                  highlights={getHighlightsForPage(pageNum)}
                  isFullPage={isFullPageHighlight(pageNum)}
                />
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}

/**
 * Landing page for tawthiq.ai
 *
 * Adapted from the Figma export in css.txt / svg.txt. Implemented as a
 * single semantic React component with responsive CSS Grid / Flex so the
 * 1920×8090 desktop layout still works on tablet and phone. All copy is
 * verbatim from the design.
 */
import "../Landing.css";

interface Props {
  onLaunchTool: () => void;
}

export default function Landing({ onLaunchTool }: Props) {
  return (
    <div className="landing-page">
      {/* ────────── Top navigation ────────── */}
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <a className="lp-brand" href="#top">
            <LogoMark />
            <span>Tawthiq</span>
          </a>
          <nav className="lp-menu">
            <a href="#about">About</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#gallery">Gallery</a>
            <a href="#team">Team</a>
            <a href="#industries">Industries</a>
          </nav>
          <button type="button" className="lp-cta-nav" onClick={onLaunchTool}>
            Tawthiq Tool
          </button>
        </div>
      </header>

      {/* ────────── Hero ────────── */}
      <section className="lp-hero" id="top">
        <div className="lp-hero-gradient" aria-hidden="true" />
        <div className="lp-hero-inner">
          <h1 className="lp-hero-title">
            From Financial Statements <br /> to Regulatory Filing
          </h1>
          <p className="lp-hero-sub">
            AI-powered compliance validation, financial data extraction, and
            XBRL generation built for GCC regulations.
          </p>
          <div className="lp-hero-actions">
            <a className="lp-btn lp-btn-primary" href="#cta">
              <BookIcon /> Book a Demo
            </a>
            <button type="button" className="lp-btn lp-btn-ghost" onClick={onLaunchTool}>
              Tawthiq Tool <ArrowRight />
            </button>
          </div>
        </div>
      </section>

      {/* ────────── Pitch ────────── */}
      <section className="lp-pitch" id="about">
        <span className="lp-badge">Fully Financial AI Compliance</span>
        <h2 className="lp-h2">Hours of Compliance Work. Minutes to Complete.</h2>
        <p className="lp-lede">
          More Than AI. Compliance Intelligence.
        </p>
        <p className="lp-paragraph">
          Tawthiq transforms complex financial reporting into a streamlined,
          automated process. From validation to XBRL generation, every step is
          designed to reduce compliance risk, improve accuracy, and accelerate
          regulatory submissions.
        </p>
        <p className="lp-paragraph">
          Whether you're an audit firm, listed company, bank, or regulator,
          Tawthiq delivers the precision and control required for today's
          evolving compliance landscape. Automate repetitive reviews, enforce
          regulatory standards, and maintain confidence in every submission.
        </p>
      </section>

      {/* ────────── Industries ────────── */}
      <section className="lp-section lp-industries" id="industries">
        <h2 className="lp-h2 lp-center">Designed for High-Stakes Financial Reporting</h2>
        <div className="lp-industries-grid">
          <IndustryCard icon={<BankIcon />} label="Banking" />
          <IndustryCard icon={<InsuranceIcon />} label="Insurance" />
          <IndustryCard icon={<BuildingIcon />} label="Listed Companies" />
          <IndustryCard icon={<RetailIcon />} label="Audit Firms" />
        </div>
      </section>

      {/* ────────── Process ────────── */}
      <section className="lp-section lp-process" id="features">
        <h2 className="lp-h2 lp-center">The Tawthiq Workflow</h2>
        <p className="lp-section-sub lp-center">
          Eliminate manual reviews, reduce filing risks, and accelerate
          regulatory submissions with intelligent automation.
        </p>
        <div className="lp-process-grid">
          <ProcessStep n={1} title="Validate" desc="Detect filing errors before regulators do." />
          <ProcessStep n={2} title="Extract" desc="Convert financial reports into structured data instantly." />
          <ProcessStep n={3} title="Map" desc="Automatically align disclosures to regulatory taxonomies." />
          <ProcessStep n={4} title="Generate" desc="Produce submission-ready XBRL packages." />
        </div>
      </section>

      {/* ────────── Business value ────────── */}
      <section className="lp-section">
        <span className="lp-eyebrow">What Makes Tawthiq Different</span>
        <h2 className="lp-h2">Up to 90% Faster Reviews</h2>
        <p className="lp-section-sub">
          Eliminate manual reviews, reduce filing risks, and accelerate
          regulatory submissions with intelligent automation.
        </p>
        <div className="lp-value-grid">
          <ValueCard
            title="Automated Rule Validation"
            desc="Complex reporting requirements. Sector-specific validation rules. Scale reviews without scaling teams."
          />
          <ValueCard
            title="Regulator-Ready Outputs"
            desc="Regulatory filing automation aligned to GCC taxonomies — XBRL packages submission-ready out of the box."
          />
          <ValueCard
            title="Audit-Ready Evidence"
            desc="Every validation linked back to source documents. Maintain a full audit trail for every decision."
          />
        </div>
      </section>

      {/* ────────── Comparison ────────── */}
      <section className="lp-section lp-compare-section">
        <span className="lp-eyebrow">Comparison</span>
        <h2 className="lp-h2">Why Tawthiq Wins?</h2>
        <p className="lp-section-sub">
          Deliver consistent reporting outcomes, reduce operational overhead,
          and stay ahead of regulatory requirements with a platform built for
          compliance excellence.
        </p>
        <div className="lp-compare-wrap">
          <table className="lp-compare">
            <thead>
              <tr>
                <th></th>
                <th className="lp-compare-us">Tawthiq</th>
                <th>Generic AI</th>
                <th>Manual Review</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Processing Time</th>
                <td className="lp-compare-us">&lt;3 min</td>
                <td>10–30 min</td>
                <td>4–8 hrs</td>
              </tr>
              <tr>
                <th>Compliance Accuracy</th>
                <td className="lp-compare-us">Yes</td>
                <td>No</td>
                <td>Manual</td>
              </tr>
              <tr>
                <th>Saudi Rules</th>
                <td className="lp-compare-us">Integrated</td>
                <td>None</td>
                <td>Manual</td>
              </tr>
              <tr>
                <th>Taxonomy Mapping</th>
                <td className="lp-compare-us">Automated</td>
                <td>Separate tools</td>
                <td>None</td>
              </tr>
              <tr>
                <th>Evidence Traceability</th>
                <td className="lp-compare-us">Built-in</td>
                <td>No</td>
                <td>Manual</td>
              </tr>
              <tr>
                <th>XBRL Generation</th>
                <td className="lp-compare-us">Full</td>
                <td>Partial</td>
                <td>Manual</td>
              </tr>
              <tr>
                <th>Arabic & English</th>
                <td className="lp-compare-us">Full</td>
                <td>Limited</td>
                <td>Partial</td>
              </tr>
              <tr>
                <th>JSON Extraction</th>
                <td className="lp-compare-us">Deterministic</td>
                <td>Variable</td>
                <td>Human-dependent</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* ────────── Why-we-win cards ────────── */}
      <section className="lp-section">
        <span className="lp-eyebrow">Business Value</span>
        <h2 className="lp-h2">Reduce Risk. Increase Confidence.</h2>
        <div className="lp-why-grid">
          <WhyCard
            icon={<CheckIcon />}
            title="Compliance First"
            desc="Built around regulatory frameworks, not generic AI."
          />
          <WhyCard
            icon={<GlobeIcon />}
            title="Arabic & English"
            desc="Native support for GCC reporting."
          />
          <WhyCard
            icon={<TraceIcon />}
            title="Evidence Traceability"
            desc="Every validation linked back to source documents."
          />
          <WhyCard
            icon={<EnterpriseIcon />}
            title="Enterprise Ready"
            desc="API integrations, cloud deployment, and secure infrastructure."
          />
        </div>
      </section>

      {/* ────────── Final CTA ────────── */}
      <section className="lp-cta-section" id="cta">
        <div className="lp-cta-card">
          <h2 className="lp-cta-title">The Future of Financial Compliance Starts Here</h2>
          <div className="lp-cta-actions">
            <button type="button" className="lp-btn lp-btn-primary" onClick={onLaunchTool}>
              See Tawthiq in Action
            </button>
            <a className="lp-btn lp-btn-outline" href="mailto:hello@azkashine.com">
              <BookIcon /> Book a Demo
            </a>
          </div>
        </div>
      </section>

      {/* ────────── Footer ────────── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-brand">
            <div className="lp-brand">
              <LogoMark />
              <span>Tawthiq</span>
            </div>
            <p>
              The Compliance Intelligence Platform for Financial Reporting and
              Regulatory Filing Automation.
            </p>
            <p className="lp-footer-location">Riyadh, Saudi Arabia</p>
          </div>

          <div className="lp-footer-cols">
            <FooterCol
              title="Platform"
              items={[
                "Document Intelligence",
                "Validation Engine",
                "Taxonomy Mapping",
                "Compliance Dashboard",
                "API Access",
              ]}
            />
            <FooterCol
              title="Solutions"
              items={[
                "Audit Firms",
                "Listed Companies",
                "Regulators",
                "Enterprise Solutions",
                "Financial Institutions",
              ]}
            />
            <FooterCol
              title="Resources"
              items={["Product Overview", "Case Studies", "Regulatory Updates"]}
            />
          </div>
        </div>

        <div className="lp-footer-bottom">
          <span>© 2026 Azkashine Private Limited. All rights reserved.</span>
          <span className="lp-footer-links">
            <a href="#terms">Terms of Service</a>
            <a href="#privacy">Privacy Policy</a>
            <a href="#cookies">Cookies</a>
          </span>
        </div>
      </footer>
    </div>
  );
}

// ─── small subcomponents ──────────────────────────────────────────────────

function IndustryCard({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="lp-industry">
      <div className="lp-industry-icon">{icon}</div>
      <span>{label}</span>
    </div>
  );
}

function ProcessStep({ n, title, desc }: { n: number; title: string; desc: string }) {
  return (
    <div className="lp-process-step">
      <div className="lp-process-num">{n}</div>
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>
  );
}

function ValueCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="lp-value-card">
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>
  );
}

function WhyCard({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="lp-why-card">
      <div className="lp-why-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>
  );
}

function FooterCol({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="lp-footer-col">
      <h4>{title}</h4>
      <ul>
        {items.map((it) => (
          <li key={it}>
            <a href={`#${it.toLowerCase().replace(/\s+/g, "-")}`}>{it}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── inline SVG icons ─────────────────────────────────────────────────────

function LogoMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 12l2 2 4-4" />
      <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
    </svg>
  );
}

function ArrowRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function BankIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2L1 7v2h22V7L12 2zM3 11v8H1v2h22v-2h-2v-8h-2v8h-3v-8h-2v8h-2v-8h-2v8H8v-8H6v8H5v-8H3z" />
    </svg>
  );
}

function InsuranceIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2L4 5v7c0 5 3.5 9.7 8 10 4.5-.3 8-5 8-10V5l-8-3zm-1 14l-4-4 1.5-1.5L11 13l5-5 1.5 1.5L11 16z" />
    </svg>
  );
}

function BuildingIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z" />
    </svg>
  );
}

function RetailIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
      <path d="M19 7h-3V5.5C16 3.6 14.4 2 12.5 2h-1C9.6 2 8 3.6 8 5.5V7H5c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zm-9-1.5c0-.8.7-1.5 1.5-1.5h1c.8 0 1.5.7 1.5 1.5V7h-4V5.5z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function TraceIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="9" y1="15" x2="15" y2="15" />
      <line x1="9" y1="11" x2="15" y2="11" />
    </svg>
  );
}

function EnterpriseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18" />
      <path d="M9 21V9" />
    </svg>
  );
}

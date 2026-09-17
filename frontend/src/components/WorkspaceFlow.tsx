import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft } from "iconoir-react";
import { Link, useLocation } from "react-router-dom";
import { ThinkingStatus } from "./ThinkingStatus";

export function WorkspaceFlow({ step, title, description, onBack, children }: {
  step: "setup" | "options" | "loading" | "results";
  title: string;
  description?: string;
  onBack?: () => void;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const location = useLocation();
  const showHomeLink = location.pathname !== "/" || step !== "setup";
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    const scrollTarget = step === "results" ? heading.current?.closest("main") : heading.current;
    scrollTarget?.scrollIntoView?.({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [step]);

  return <main className={`product-workspace step-workspace step-${step}`} id="main-content">
    <div className="flow-navigation">
      <div className="flow-back-actions">{showHomeLink && <Link className="back-link" to="/" reloadDocument><ArrowLeft aria-hidden="true"/> Back to home</Link>}{onBack && <button className="back-link" onClick={onBack}>Edit setup</button>}</div>
      <ol className="flow-steps" aria-label="Progress">
        {(["setup", "options", "loading", "results"] as const).map((item, index) => <li key={item} aria-current={step === item ? "step" : undefined}><span>{index + 1}</span>{["Upload", "Options", "Processing", "Results"][index]}</li>)}
      </ol>
    </div>
    <header className="flow-heading"><h1 ref={heading} tabIndex={-1}>{title}</h1>{description && <p>{description}</p>}</header>
    {children}
    {step === "setup" && location.pathname === "/" && <footer className="flow-boundary"><p>Research prototype for selected FDA/CDER reuse checks. This demonstration explores prospective forward compatibility, which is not currently operational. Results do not establish submission readiness or FDA acceptance and have not been validated by a regulatory expert.</p></footer>}
  </main>;
}

export function FlowLoading({ label, detail, error, onRetry }: { label: string; detail: string; error?: string | null; onRetry?: () => void }) {
  return <section className="flow-loading">
    <ThinkingStatus label={label} state="solving" size={64} paused={Boolean(error)}/>
    <p>{detail}</p>
    {error && <div className="flow-error" role="alert"><p>{error}</p><p>The run may still be processing. Check its status again to continue.</p><button className="secondary-button" onClick={onRetry}>Check status again</button></div>}
  </section>;
}

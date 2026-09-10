import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft, WarningTriangle } from "iconoir-react";
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
  const showHomeLink = location.pathname !== "/";
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
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
    {step !== "loading" && <aside className="flow-boundary"><WarningTriangle aria-hidden="true"/><p>FDA/CDER research prototype. Forward compatibility is currently unavailable. Findings support review and do not establish FDA acceptance or submission readiness. Not validated by a regulatory expert.</p></aside>}
  </main>;
}

export function FlowLoading({ label, detail, error, onRetry }: { label: string; detail: string; error?: string | null; onRetry?: () => void }) {
  return <section className="flow-loading">
    <ThinkingStatus label={label} state="solving" size={64} paused={Boolean(error)}/>
    <p>{detail}</p>
    {error && <div className="flow-error" role="alert"><p>{error}</p><p>The run may still be processing. Check its status again to continue.</p><button className="secondary-button" onClick={onRetry}>Check status again</button></div>}
  </section>;
}

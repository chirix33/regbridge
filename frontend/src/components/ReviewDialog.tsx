import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Xmark } from "iconoir-react";

/** Native modal semantics keep the background inert and contain keyboard focus. */
export function ReviewDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [closing, setClosing] = useState(false);
  const closeCallback = useRef(onClose);
  useEffect(() => { closeCallback.current = onClose; });
  useEffect(() => {
    const dialog = ref.current!;
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(() => closeCallback.current(), window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : 200);
    return () => window.clearTimeout(timer);
  }, [closing]);
  return createPortal(<dialog ref={ref} className="review-dialog" data-closing={closing} aria-modal="true" aria-labelledby={titleId} onCancel={e => { e.preventDefault(); setClosing(true); }} onKeyDown={e => {
    if (e.key !== "Tab") return;
    // Native modality makes the page inert; explicitly wrap before browser chrome.
    const controls = [...e.currentTarget.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, summary, [tabindex]")].filter(el => el.tabIndex >= 0 && !el.hasAttribute("disabled") && el.getClientRects().length > 0);
    const first = controls[0], last = controls.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }}>
    <header className="dialog-header"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label="Close document review" onClick={() => setClosing(true)}><Xmark aria-hidden="true"/></button></header>
    <div className="dialog-content">{children}</div>
  </dialog>, document.body);
}

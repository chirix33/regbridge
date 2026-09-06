import { useState } from "react";
import { Menu, Xmark } from "iconoir-react";
import { Link, NavLink } from "react-router-dom";

export function ProductNav() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="product-nav" data-menu-open={open} aria-label="RegBridge workspace navigation">
      <Link className="brand" to="/" aria-label="RegBridge Analyzer home"><span className="brand-mark" aria-hidden="true">R</span><span>RegBridge</span></Link>
      <button
        className="mobile-nav-toggle"
        type="button"
        aria-controls="product-nav-links"
        aria-expanded={open}
        aria-label={open ? "Close navigation menu" : "Open navigation menu"}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <Xmark aria-hidden="true" /> : <Menu aria-hidden="true" />}
      </button>
      <div className="product-nav-links" id="product-nav-links" onClick={() => setOpen(false)}>
        <NavLink to="/" end>Analyzer</NavLink>
        <NavLink to="/baselines">Baselines</NavLink>
        <NavLink to="/evaluation">Evaluation</NavLink>
        <NavLink to="/demo/case-a">Guided cases</NavLink>
        <NavLink to="/about">About</NavLink>
      </div>
    </nav>
  );
}

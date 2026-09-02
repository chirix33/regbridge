import { Link, NavLink } from "react-router-dom";

export function ProductNav() {
  return (
    <nav className="product-nav" aria-label="RegBridge workspace navigation">
      <Link className="brand" to="/" aria-label="RegBridge Analyzer home"><span className="brand-mark" aria-hidden="true">R</span><span>RegBridge</span></Link>
      <div className="product-nav-links">
        <NavLink to="/" end>Analyzer</NavLink>
        <NavLink to="/baselines">Baselines</NavLink>
        <NavLink to="/evaluation">Evaluation</NavLink>
        <NavLink to="/demo/case-a">Guided cases</NavLink>
        <NavLink to="/about">About</NavLink>
      </div>
    </nav>
  );
}

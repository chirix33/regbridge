import type { GraphNeighborhood as GraphData } from "../api/contracts";

const nodeOrder = ["artifact", "heading", "keyword", "dossier_evidence", "standard_version", "rule", "model_finding", "evidence", "repair", "decision"];

export function GraphNeighborhood({ graph }: { graph: GraphData }) {
  const grouped = nodeOrder
    .map((type) => ({ type, nodes: graph.nodes.filter((node) => node.type === type) }))
    .filter((group) => group.nodes.length);

  return (
    <section className="result-section" aria-labelledby="graph-title">
      <div className="result-heading">
        <p className="panel-kicker">Typed neighborhood</p>
        <h2 id="graph-title">Why this conclusion is connected</h2>
      </div>
      <div className="graph-board" role="img" aria-describedby="graph-text-alternative">
        {grouped.map((group) => (
          <div className="graph-column" key={group.type}>
            <h3>{group.type.replaceAll("_", " ")}</h3>
            {group.nodes.map((node) => (
              <article className={`graph-node node-${node.type}`} key={node.id}>
                <strong>{node.label}</strong>
                <span>{node.review_status ?? "parsed source fact"}</span>
              </article>
            ))}
          </div>
        ))}
      </div>
      <details className="text-alternative" id="graph-text-alternative">
        <summary>Read graph relationships as text</summary>
        <ul>
          {graph.text_alternative.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </details>
    </section>
  );
}

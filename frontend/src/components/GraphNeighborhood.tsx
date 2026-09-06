import { useId } from "react";

import type { GraphNeighborhood as GraphData } from "../api/contracts";

const nodeOrder = ["artifact", "heading", "keyword", "dossier_evidence", "standard_version", "rule", "model_finding", "analysis_limitation", "evidence", "repair", "decision"];

export function GraphNeighborhood({ graph }: { graph: GraphData }) {
  // The dossier workspace renders one of these per analyzed document, so the
  // ids these labels point at have to be unique per instance.
  const instanceId = useId();
  const titleId = `graph-title-${instanceId}`;
  const textAlternativeId = `graph-text-alternative-${instanceId}`;
  const grouped = nodeOrder
    .map((type) => ({ type, nodes: graph.nodes.filter((node) => node.type === type) }))
    .filter((group) => group.nodes.length);

  return (
    <section className="result-section" aria-labelledby={titleId}>
      <div className="result-heading">
        <p className="panel-kicker">Typed neighborhood</p>
        <h2 id={titleId}>Why this conclusion is connected</h2>
      </div>
      <div
        className="graph-board"
        role="img"
        aria-label="Typed graph neighborhood diagram. The same relationships are listed as text below."
        aria-describedby={textAlternativeId}
        tabIndex={0}
      >
        {grouped.map((group) => (
          <div className="graph-column" key={group.type}>
            <h3>{group.type.replaceAll("_", " ")}</h3>
            {group.nodes.map((node) => (
              <article className={`graph-node node-${node.type}`} key={node.id}>
                <strong>{node.label}</strong>
                <span>{node.type === "analysis_limitation" ? "non-regulatory execution status" : node.review_status ?? "parsed source fact"}</span>
              </article>
            ))}
          </div>
        ))}
      </div>
      <details className="text-alternative" id={textAlternativeId}>
        <summary>Read graph relationships as text</summary>
        <ul>
          {graph.text_alternative.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </details>
      <div
        className="table-scroll graph-edge-table"
        role="region"
        aria-label="Graph edge relationships"
        tabIndex={0}
      >
        <table className="metrics-table compact" aria-label="Graph edge table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Edge</th>
              <th>Target</th>
              <th>Review status</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {graph.edges.map((edge) => {
              const source = graph.nodes.find((node) => node.id === edge.source);
              const target = graph.nodes.find((node) => node.id === edge.target);
              return (
                <tr key={edge.id}>
                  <td>{source?.label ?? edge.source}</td>
                  <td>{edge.type}</td>
                  <td>{target?.label ?? edge.target}</td>
                  <td>{edge.review_status ?? "parsed source fact"}</td>
                  <td>{edge.evidence_ids.join(", ") || "none"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

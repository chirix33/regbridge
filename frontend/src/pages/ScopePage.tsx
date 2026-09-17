export function ScopePage() {
  return <main id="main-content" className="product-workspace about-page">
    <h1>About RegBridge</h1>
    <p>RegBridge helps reviewers examine selected FDA/CDER Module 3 content for prospective eCTD v3.2.2 to v4.0 reuse. It brings recorded observations, proposed actions, affected documents, and supporting evidence into one review workspace.</p>
    <h2>How a review works</h2>
    <ol className="about-sequence">
      <li><h3>Read the dossier</h3><p>Parse the selected package and identify document context, metadata, and available text.</p></li>
      <li><h3>Check pinned standards</h3><p>Apply the supported placement and metadata checks within the selected policy coverage.</p></li>
      <li><h3>Inspect content</h3><p>Use evidence-bounded AI assistance where applicable. Incomplete inspection remains visible.</p></li>
      <li><h3>Explain the recommendation</h3><p>Combine the recorded checks and findings, preserving the evidence, unresolved conditions, and required human approval.</p></li>
    </ol>
  </main>;
}

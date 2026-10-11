type PlaceholderPageProps = { eyebrow: string; title: string; description: string; items: string[] }

export function PlaceholderPage({ eyebrow, title, description, items }: PlaceholderPageProps) {
  return (
    <section className="page-stack">
      <header className="page-header"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></header>
      <div className="placeholder-card">
        <div className="placeholder-icon">+</div>
        <div><h2>Workspace coming next</h2><p>This section is ready for the next product workflow.</p></div>
        <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </section>
  )
}

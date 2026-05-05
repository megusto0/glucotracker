type Crumb = { label: string; to?: string };

export default function PageHead({
  crumbs,
  title,
  right,
}: {
  crumbs?: Crumb[];
  title: string;
  right?: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 24 }}>
      {crumbs && (
        <div className="gt-crumbs">
          {crumbs.map((c, i) => (
            <span key={i}>
              {c.to ? (
                <a href={c.to} style={{ color: "var(--ink-4)", textDecoration: "none" }}>
                  {c.label}
                </a>
              ) : (
                c.label
              )}
            </span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <h1 className="gt-h1">{title}</h1>
        {right && <div>{right}</div>}
      </div>
    </div>
  );
}

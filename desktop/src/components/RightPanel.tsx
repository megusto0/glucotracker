import { X } from "lucide-react";

export default function RightPanel({
  title,
  subtitle,
  onClose,
  children,
}: {
  title?: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="gt-rightpanel">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 18 }}>
        <div>
          {title && <h2>{title}</h2>}
          {subtitle && (
            <div className="lbl" style={{ marginTop: 4 }}>{subtitle}</div>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--ink-3)", padding: 4, display: "flex", alignItems: "center",
          }}
        >
          <X size={16} />
        </button>
      </div>
      {children}
    </div>
  );
}

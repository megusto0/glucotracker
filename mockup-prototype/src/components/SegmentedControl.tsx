export default function SegmentedControl({ items, value, onChange }: {
  items: string[]; value: string; onChange: (v: string) => void
}) {
  return (
    <div className="seg">
      {items.map((it) => (
        <button key={it} className={it === value ? "on" : ""} onClick={() => onChange(it)}>
          {it}
        </button>
      ))}
    </div>
  )
}

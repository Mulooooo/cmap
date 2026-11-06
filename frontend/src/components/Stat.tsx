export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

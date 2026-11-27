const TILES = [
  "New enquiries",
  "Quotes awaiting approval",
  "Quotes sent",
  "Replies to review",
  "Awaiting signed contract",
  "Deposits to verify",
  "Outstanding balances",
  "Held form submissions",
  "Failed automations",
];

export default function Dashboard() {
  return (
    <div>
      <h1 className="font-serif text-2xl text-stone-900">Dashboard</h1>
      <p className="mt-1 text-stone-600">Counts fill in as each phase lands.</p>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {TILES.map((t) => (
          <div key={t} className="rounded-lg border border-stone-200 bg-white p-5">
            <div className="text-sm text-stone-500">{t}</div>
            <div className="mt-2 text-3xl font-semibold text-stone-300">0</div>
          </div>
        ))}
      </div>
    </div>
  );
}

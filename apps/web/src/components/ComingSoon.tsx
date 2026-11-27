import { ALL_ITEMS } from "@/lib/nav";

export function ComingSoon({ href }: { href: string }) {
  const item = ALL_ITEMS.find((i) => i.href === href);
  if (!item) return null;
  return (
    <div>
      <h1 className="font-serif text-2xl text-stone-900">{item.label}</h1>
      <p className="mt-1 text-stone-600">{item.summary}</p>
      <div className="mt-8 rounded-lg border border-dashed border-stone-300 bg-white p-8 text-stone-500">
        This screen is built in Phase {item.phase}.
      </div>
    </div>
  );
}

export const fmt = (cents: number | null | undefined) =>
  cents == null
    ? "—"
    : `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: cents % 100 ? 2 : 0 })}`;

export const toCents = (dollars: string) => Math.round(parseFloat(dollars || "0") * 100);
export const toDollars = (cents: number | null | undefined) => (cents == null ? "" : String(cents / 100));

// Public form pages, embedded on the Jstyle WordPress site in an iframe. No sign-in.
export default function FormsLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-white px-4 py-6 text-stone-900">{children}</div>;
}

import { AccountBar } from "@/components/AccountBar";
import { Sidebar } from "@/components/Sidebar";

// Highest phase whose screens are live. Bumped as phases land.
const CURRENT_PHASE = 8;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-stone-50">
      <Sidebar current={CURRENT_PHASE} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AccountBar />
        <main className="mx-auto w-full max-w-7xl flex-1 px-8 py-8">{children}</main>
      </div>
    </div>
  );
}

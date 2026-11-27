import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jstyle Business OS",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased text-stone-900">{children}</body>
    </html>
  );
}

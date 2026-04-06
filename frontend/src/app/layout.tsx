import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Flight Delay Analyzer",
  description: "Understand why your flight is delayed — rotation tracing, FAA conditions, root-cause analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-950 text-slate-100 min-h-screen`}>
        <header className="border-b border-slate-800 px-6 py-4 flex items-center gap-3">
          <span className="text-2xl">✈️</span>
          <span className="font-semibold text-lg tracking-tight">Flight Delay Analyzer</span>
          <span className="ml-auto text-xs text-slate-500">Powered by FlightAware AeroAPI + FAA NAS</span>
        </header>
        <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}

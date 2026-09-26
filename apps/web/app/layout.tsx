import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Yousuf Rice — Call Grader & Coaching AI",
  description: "Internal call quality operations dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}

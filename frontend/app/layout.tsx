import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "uxr-agent",
  description:
    "A self-deployed UX research portfolio agent. Ask questions, get answers grounded in real case stories.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

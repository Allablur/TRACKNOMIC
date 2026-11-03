import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Trackonomics",
  description: "Music industry analytics, built on attributed data.",
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

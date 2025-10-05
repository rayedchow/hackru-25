import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "Synapse",
  description: "Personal intelligence system with screenshot integration",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="dark"
      style={{
        // @ts-ignore
        "--font-geist-sans": GeistSans.style.fontFamily,
        "--font-geist-mono": GeistMono.style.fontFamily,
      }}
    >
      <body
        className={`font-sans antialiased`}
        style={{
          fontFamily: GeistSans.style.fontFamily,
        }}
      >
        {children}
      </body>
    </html>
  );
}

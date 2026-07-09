import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-qiko" });

export const metadata: Metadata = {
  title: "Qiko | Build & Sell Custom AI Digital Workers",
  description: "You bring the niche expertise. Qiko handles models, GPUs and security so you can launch a production ready digital worker.",
  icons: { icon: "/qiko-icon.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        {/* Qiko brand display font (Satoshi) */}
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700,900&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";

import { AUTH_MODE } from "@/lib/config";

import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// Headings: a warm, classic serif that suits legal work.
const display = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TheContrAIct",
  description: "Contract deadlines, notice periods and invoicing alerts, powered by AI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const app = <Providers>{children}</Providers>;
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${display.variable} h-full antialiased`}
    >
      <body className="min-h-full font-sans">
        {AUTH_MODE === "clerk" ? <ClerkProvider>{app}</ClerkProvider> : app}
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME || "Kayak DMV",
  description: "Compare apartments by true rent, fees, concessions, and negotiation leverage.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

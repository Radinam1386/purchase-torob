import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/500.css";
import "@fontsource/vazirmatn/600.css";
import "@fontsource/vazirmatn/700.css";
import "leaflet/dist/leaflet.css";
import "./globals.css";

import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "ترب حضوری | راهنمای خرید در تهران",
  description: "محصول را پیدا کن، فروشگاه‌های نزدیک را مقایسه کن و با خیال راحت حضوری خرید کن.",
  applicationName: "ترب حضوری",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f7f6f2",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning data-scroll-behavior="smooth">
      <body>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("torob-theme");if(t==="dark"||((!t||t==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches)){document.documentElement.dataset.theme="dark"}}catch(e){}`,
          }}
        />
        {children}
      </body>
    </html>
  );
}

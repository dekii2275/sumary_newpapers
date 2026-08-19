import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Tech News",
  description: "AI and technology news intelligence platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body style={{ margin: 0, fontFamily: "Arial, sans-serif" }}>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { QueryProvider } from "@/lib/query-client";
import { TopNav } from "@/components/terminal/TopNav";

export const metadata: Metadata = {
  title: "Confluence Trading Consultant",
  description: "AI-assisted, human-decides crypto trading terminal.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-bg text-primary antialiased min-h-screen">
        <AuthProvider>
          <QueryProvider>
            <TopNav />
            <div className="pt-12">{children}</div>
          </QueryProvider>
        </AuthProvider>
      </body>
    </html>
  );
}

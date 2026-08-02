import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Referral Program',
  description: 'Check your referral status and earnings.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b bg-white">
          <nav className="max-w-4xl mx-auto flex items-center justify-between px-4 py-3">
            <Link href="/" className="font-semibold text-brand">
              Referral Program
            </Link>
            <div className="flex gap-4 text-sm text-gray-600">
              <Link href="/check">Check Status</Link>
              <Link href="/faq">FAQ</Link>
            </div>
          </nav>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-8">{children}</main>
        <footer className="border-t mt-12 py-6 text-center text-xs text-gray-400">
          <div className="max-w-4xl mx-auto px-4 flex justify-center gap-4">
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
          </div>
        </footer>
      </body>
    </html>
  );
}

import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'Shuddho Draft Lab', description: 'AI writing assistant MVP' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

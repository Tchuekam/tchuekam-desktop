import './globals.css';
import { Inter } from "next/font/google";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata = {
  title: 'Genimage — AI Image & Video Studio',
  description: 'Generate AI images and videos using 200+ models.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.variable} suppressHydrationWarning>{children}</body>
    </html>
  );
}

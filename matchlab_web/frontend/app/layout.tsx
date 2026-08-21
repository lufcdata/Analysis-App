import './globals.css';

export const metadata = {
  title: 'MatchLab V2',
  description: 'Football match, player and metric leader graphics',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

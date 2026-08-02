// Simple placeholder ad slot. In production, replace the inner div with the
// actual AdSense <ins> tag or Monetag script for the given zone/slot id.
// Ads only ever appear on the public website (never inside Telegram) and
// exist purely to cover hosting costs — they have no connection to payout math.
export function AdSlot({ label, height = 90 }: { label: string; height?: number }) {
  return (
    <div className="ad-slot" style={{ height }}>
      Ad space — {label}
    </div>
  );
}

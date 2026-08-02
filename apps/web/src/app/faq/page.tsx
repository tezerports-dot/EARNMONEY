import { AdSlot } from '@/components/AdSlot';

const faqs = [
  {
    q: 'How do I join?',
    a: 'Open the referral link a friend sends you — it opens Telegram and starts our bot. Share your phone number when asked, then join both the channel and group it gives you.',
  },
  {
    q: 'When does my account become active?',
    a: 'After you have stayed in both the assigned channel and group continuously for 24 hours.',
  },
  {
    q: 'How much do I earn?',
    a: "You earn a flat rate (set monthly by the admin, between ₹1 and ₹5) for every referral of yours that is active that month.",
  },
  {
    q: 'How do I get paid?',
    a: 'Send /bankdetails to the bot to add your bank account or UPI ID. Payouts are calculated on the 1st of each month and transferred by the team shortly after.',
  },
  {
    q: 'Why did my account become inactive?',
    a: 'If you leave the assigned channel or group for 72+ hours, your account is marked inactive until you rejoin.',
  },
];

export default function FaqPage() {
  return (
    <div>
      <AdSlot label="header" height={90} />
      <h1 className="text-2xl font-bold mb-6">Frequently Asked Questions</h1>
      <div className="space-y-4">
        {faqs.map((f) => (
          <div key={f.q} className="card">
            <h3 className="font-semibold mb-1">{f.q}</h3>
            <p className="text-sm text-gray-600">{f.a}</p>
          </div>
        ))}
      </div>
      <AdSlot label="footer" height={90} />
    </div>
  );
}

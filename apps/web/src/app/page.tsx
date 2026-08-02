import Link from 'next/link';
import { AdSlot } from '@/components/AdSlot';

export default function HomePage() {
  return (
    <div>
      <AdSlot label="header" height={90} />

      <section className="card text-center py-12">
        <h1 className="text-3xl font-bold mb-3">Invite friends. Get paid monthly.</h1>
        <p className="text-gray-600 max-w-xl mx-auto mb-6">
          Join our Telegram community, invite friends with your personal link, and earn a flat rate for every
          active referral — paid straight to your bank account each month.
        </p>
        <Link href="/check" className="btn-primary inline-block">
          Check My Status
        </Link>
      </section>

      <AdSlot label="in-content" height={250} />

      <section className="grid sm:grid-cols-3 gap-4 mt-8">
        <div className="card">
          <h3 className="font-semibold mb-2">1. Join via Telegram</h3>
          <p className="text-sm text-gray-600">
            Start a chat with our bot using a referral link, verify your phone number, and join your assigned
            channel and group.
          </p>
        </div>
        <div className="card">
          <h3 className="font-semibold mb-2">2. Invite friends</h3>
          <p className="text-sm text-gray-600">
            Once verified you get your own referral code and link to share.
          </p>
        </div>
        <div className="card">
          <h3 className="font-semibold mb-2">3. Get paid monthly</h3>
          <p className="text-sm text-gray-600">
            Add your bank details in the bot with <code>/bankdetails</code> and receive a payout every month based
            on your active referrals.
          </p>
        </div>
      </section>

      <AdSlot label="footer" height={90} />
    </div>
  );
}

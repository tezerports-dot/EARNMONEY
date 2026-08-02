export default function PrivacyPage() {
  return (
    <div className="card prose max-w-none">
      <h1 className="text-2xl font-bold mb-4">Privacy Policy</h1>
      <p className="text-sm text-gray-600 mb-3">
        We collect your Telegram ID, username, phone number, and (only via the bot, never the website) your bank
        account or UPI details, in order to run the referral program and pay out earnings.
      </p>
      <p className="text-sm text-gray-600 mb-3">
        Bank details are never collected or displayed on this website — they are only ever entered through the
        Telegram bot's /bankdetails command and used by administrators to process monthly payouts.
      </p>
      <p className="text-sm text-gray-600">
        This site displays third-party ads to cover hosting costs. Ad providers may use cookies to serve relevant
        ads; see their respective privacy policies for details.
      </p>
    </div>
  );
}

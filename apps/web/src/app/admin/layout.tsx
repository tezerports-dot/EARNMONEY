import Link from 'next/link';
import { LogoutButton } from '@/components/LogoutButton';

const navItems = [
  { href: '/admin/dashboard', label: 'Dashboard' },
  { href: '/admin/users', label: 'Users' },
  { href: '/admin/channels', label: 'Channels' },
  { href: '/admin/groups', label: 'Groups' },
  { href: '/admin/payouts', label: 'Payouts' },
  { href: '/admin/audit-logs', label: 'Audit Logs' },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-6">
      <aside className="space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="block px-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-100"
          >
            {item.label}
          </Link>
        ))}
        <div className="pt-2">
          <LogoutButton />
        </div>
      </aside>
      <section>{children}</section>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { House, Search, Sparkles } from "lucide-react";

const TABS = [
  { href: "/", label: "خانه", icon: House },
  { href: "/products", label: "محصولات", icon: Search },
  { href: "/chat", label: "دستیار خرید", icon: Sparkles },
];

export function MobileNav() {
  const pathname = usePathname();
  if (pathname.startsWith("/seller-sim")) return null;

  return (
    <nav className="mobile-bottom-nav" aria-label="ناوبری سریع">
      {TABS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={active ? "active" : ""}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={20} strokeWidth={active ? 2.4 : 2} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

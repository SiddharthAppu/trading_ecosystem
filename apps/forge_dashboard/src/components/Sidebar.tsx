/* ── Navigation sidebar ── */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/chart", label: "Chart", icon: "📈" },
  { href: "/backtest", label: "Backtest", icon: "🧪" },
  { href: "/runtime", label: "Runtime", icon: "🖥️" },
  { href: "/journal", label: "Journal", icon: "📒" },
  { href: "/config", label: "Config", icon: "⚙️" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 w-56 h-screen bg-[#151528] border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-800">
        <h1 className="text-lg font-bold text-white tracking-tight">
          Strategy<span className="text-blue-500">Forge</span>
        </h1>
        <p className="text-[10px] text-gray-500 mt-0.5">
          Backtest · Paper · Live
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-blue-600/20 text-blue-400"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-gray-800 text-[10px] text-gray-600">
        StrategyForge v0.8
      </div>
    </aside>
  );
}

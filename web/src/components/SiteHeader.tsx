import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <Link href="/" className="text-lg font-semibold text-ink-950">
          {process.env.NEXT_PUBLIC_APP_NAME || "Kayak DMV"}
        </Link>
        <nav className="flex flex-wrap gap-4 text-sm font-medium text-sea-600">
          <Link href="/specials">Specials</Link>
          <Link href="/calculator">Calculator</Link>
          <Link href="/search">Search</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/account">Account</Link>
          <Link href="/login">Log in</Link>
        </nav>
      </div>
    </header>
  );
}

"use client";

import Link from "next/link";

import { CreateOrganization } from "@/components/app/create-organization";

export default function NewOrganizationPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-4">
      <CreateOrganization />
      <Link href="/app" className="text-muted text-sm hover:underline">
        Cancel
      </Link>
    </main>
  );
}

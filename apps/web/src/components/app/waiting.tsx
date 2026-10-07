"use client";

import { useEffect, useState } from "react";

import { Loading } from "@/components/ui";

/**
 * A spinner that explains itself after a few seconds: on free hosting the API sleeps when
 * unused and takes up to a minute to wake.
 */
export function Waiting() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <Loading />
      {slow && (
        <p className="text-muted max-w-xs text-sm">
          Starting up. After a quiet spell this can take up to a minute.
        </p>
      )}
    </div>
  );
}

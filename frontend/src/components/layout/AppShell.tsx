import { PropsWithChildren } from "react";

import { TopBar } from "./TopBar";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto max-w-[1600px] px-6 py-6">{children}</main>
    </div>
  );
}

"use client";

import { useEffect } from "react";
import { ShoppingWorkspace } from "@/components/shopping-workspace";

export default function ChatPage() {
  useEffect(() => {
    const q = new URLSearchParams(location.search).get("q");
    if (q) sessionStorage.setItem("torob-chat-initial", q);
  }, []);
  return <ShoppingWorkspace />;
}

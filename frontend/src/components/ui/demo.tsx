import React from "react";
import RuixenMoonChat from "./ruixen-moon-chat";

export default function DemoPage() {
  return (
    <main className="min-h-screen w-full bg-black text-white flex flex-col justify-between">
      {/* Chat Component */}
      <section className="flex-1 flex justify-center items-start w-full">
        <RuixenMoonChat activeConversation={null} onChatUpdated={() => {}} />
      </section>

      {/* Footer */}
      <footer className="text-center text-neutral-500 py-4 border-t border-neutral-800 text-sm bg-neutral-950">
        © {new Date().getFullYear()} Ruixen Demo Page
      </footer>
    </main>
  );
}

// What the glasses user setup collects, in memory until Upload on the Voice step.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { loadGlassesUser, syncGlassesUser } from "../../api/glassesUser";
import { previewEnabled, sampleRecording } from "../../dev/preview";
import type { Recording } from "../../lib/recording";

interface GlassesUserFlow {
  name: string;
  setName: (name: string) => void;
  context: string;
  setContext: (context: string) => void;
  voice: Recording | null;
  setVoice: (voice: Recording | null) => void;
  /** The name shown on All set, once Upload succeeded. */
  doneName: string | null;
  setDoneName: (name: string) => void;
}

const Context = createContext<GlassesUserFlow | null>(null);

export function GlassesUserFlowProvider({ children }: { children: ReactNode }) {
  // Coming back to setup in the same browser starts from what was saved last time.
  const [saved] = useState(() => loadGlassesUser());
  const [preview] = useState(previewEnabled);
  const [name, setName] = useState(saved?.name ?? (preview ? "Rose" : ""));
  const [context, setContext] = useState(saved?.context ?? "");
  const [voice, setVoiceState] = useState<Recording | null>(() => (preview ? sampleRecording() : null));
  const [doneName, setDoneName] = useState<string | null>(null);

  // A user the API already knows fills the name in, unless something was typed already. The
  // name remembered in this browser gives way too: the API is where a rename (the manage pages)
  // lands, and keeping the old copy here would write it back over the new name on Upload.
  useEffect(() => {
    if (preview) return;
    let cancelled = false;
    const remembered = saved?.name ?? "";
    void syncGlassesUser().then((user) => {
      if (user && !cancelled) setName((current) => (current.trim() && current !== remembered ? current : user.name));
    });
    return () => {
      cancelled = true;
    };
  }, [preview]);

  const setVoice = useCallback((next: Recording | null) => {
    setVoiceState((previous) => {
      if (previous && previous !== next) URL.revokeObjectURL(previous.url);
      return next;
    });
  }, []);

  // Leaving setup frees the recording; deferred past StrictMode's test unmount (see visitor/state.tsx).
  const latestVoice = useRef(voice);
  latestVoice.current = voice;
  const pendingRelease = useRef(0);
  useEffect(() => {
    window.clearTimeout(pendingRelease.current);
    return () => {
      pendingRelease.current = window.setTimeout(() => {
        if (latestVoice.current) URL.revokeObjectURL(latestVoice.current.url);
      });
    };
  }, []);

  const value = useMemo(
    () => ({ name, setName, context, setContext, voice, setVoice, doneName, setDoneName }),
    [name, context, voice, setVoice, doneName],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useGlassesUserFlow(): GlassesUserFlow {
  const flow = useContext(Context);
  if (!flow) throw new Error("useGlassesUserFlow must be used inside GlassesUserFlowProvider");
  return flow;
}

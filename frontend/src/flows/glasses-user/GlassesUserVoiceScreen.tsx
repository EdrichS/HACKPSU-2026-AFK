import { useState } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { saveGlassesUser } from "../../api/glassesUser";
import { Button } from "../../components/Button";
import { VoicePrompt } from "../../components/Cards";
import { ActionBar, FormMain, Notice, PageShell, TitleBlock } from "../../components/PageShell";
import { Recorder } from "../../components/Recorder";
import { useRecorder } from "../../lib/useRecorder";
import { useGlassesUserFlow } from "./state";

export function GlassesUserVoiceScreen() {
  const flow = useGlassesUserFlow();
  const navigate = useNavigate();
  const recorder = useRecorder(flow.voice);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const name = flow.name.trim();

  const upload = async () => {
    const recording = recorder.handOff();
    if (!recording) return;
    flow.setVoice(recording);
    setBusy(true);
    setFailure(null);
    try {
      const result = await saveGlassesUser({ name, context: flow.context.trim() }, recording.wav);
      flow.setDoneName(result.name);
      navigate("/setup/done", { replace: true });
    } catch (e) {
      // Upload's error and offline states aren't designed; same plain notice as About you. The
      // server's own sentences (a recording with too little speech, a bad name) are shown as is.
      let message = "We couldn't save your setup. Please press Upload to try again.";
      if (e instanceof ApiError && e.status === 0) message = "You seem to be offline. Check your connection, then press Upload again.";
      else if (e instanceof ApiError && e.status === 422) message = `${e.message} Press Retry to record again.`;
      else if (e instanceof ApiError && e.status >= 400) message = e.message;
      setFailure(message);
      setBusy(false);
    }
  };

  return (
    <PageShell
      title="Your voice"
      step={{ current: 3, total: 3 }}
      footer={
        <ActionBar>
          <Button variant="secondary" icon="rotate-ccw" disabled={!recorder.canRetry || busy} onClick={recorder.retry}>
            Retry
          </Button>
          <Button icon="upload" busy={busy} disabled={!recorder.ready} onClick={upload}>
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={780}>
        <TitleBlock title="Read this out loud" lead="This helps your glasses tell your voice apart from the people around you." />
        <VoicePrompt
          text={`Hello, this is ${name}. I'm reading this so my glasses can learn what my own voice sounds like. On quiet mornings I like to sit by the window with a warm cup of tea and watch the street wake up. When my family calls, I want to catch every word they say.`}
        />
        <Recorder recorder={recorder} />
        {failure && <Notice>{failure}</Notice>}
      </FormMain>
    </PageShell>
  );
}

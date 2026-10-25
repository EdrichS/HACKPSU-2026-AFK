import { useNavigate } from "react-router";

import { Button } from "../../components/Button";
import { VoicePrompt } from "../../components/Cards";
import { ActionBar, FormMain, PageShell, TitleBlock } from "../../components/PageShell";
import { Recorder } from "../../components/Recorder";
import { possessive } from "../../config";
import { useRecorder } from "../../lib/useRecorder";
import { useVisitorFlow } from "./state";

export function VisitorVoiceScreen() {
  const flow = useVisitorFlow();
  const navigate = useNavigate();
  const recorder = useRecorder(flow.voice);
  const rose = flow.glassesUserName;

  const next = () => {
    const recording = recorder.handOff();
    if (!recording) return;
    flow.setVoice(recording);
    navigate("/visitor/about");
  };

  return (
    <PageShell
      title="Voice"
      step={{ current: 3, total: 4 }}
      footer={
        <ActionBar>
          <Button variant="secondary" icon="rotate-ccw" disabled={!recorder.canRetry} onClick={recorder.retry}>
            Retry
          </Button>
          <Button icon="arrow-right" iconAfter disabled={!recorder.ready} onClick={next}>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={780}>
        {/* The design copy says "her glasses"; the name is used instead, since pronouns aren't collected. */}
        <TitleBlock
          title="Read this out loud"
          lead={`Read at your normal pace, like you're talking to ${rose}. This teaches ${possessive(rose)} glasses what your voice sounds like.`}
        />
        <VoicePrompt
          text={`Hi ${rose}, it's me. I'm reading this so your glasses can learn the sound of my voice. Most weekends I go for long walks, try a new recipe, and catch up with family. If you ever forget my name, listen for this voice and you'll know it's me.`}
        />
        <Recorder recorder={recorder} />
      </FormMain>
    </PageShell>
  );
}

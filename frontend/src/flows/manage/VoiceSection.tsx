// The person's voice recordings: play, delete, record another. Not designed.

import { useState } from "react";

import { ApiError, checkVoice, deleteVoice, getPerson, uploadVoice, voiceAudioUrl } from "../../api/client";
import type { Person, VoiceSample } from "../../api/contract";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icon";
import { Notice } from "../../components/PageShell";
import { Recorder } from "../../components/Recorder";
import { useRecorder } from "../../lib/useRecorder";
import styles from "./manage.module.css";
import { describe, isGlassesUser, Section, shortDate } from "./shared";

interface VoiceSectionProps {
  person: Person;
  samples: VoiceSample[];
  setSamples: (update: (samples: VoiceSample[]) => VoiceSample[]) => void;
  onPerson: (person: Person) => void;
}

/** One take: the recorder plus a Save button. Remounted (by key) after a save so it starts fresh. */
function NewRecording({ person, onSaved }: { person: Person; onSaved: (sample: VoiceSample) => void }) {
  const recorder = useRecorder();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const save = async () => {
    const recording = recorder.recording;
    if (!recording) return;
    setBusy(true);
    setFailure(null);
    try {
      const check = await checkVoice(recording.wav);
      if (check && !check.ok) throw new ApiError(422, check.reason);
      const out = await uploadVoice(person.id, recording.wav);
      onSaved({ voice_sample_id: out.voice_sample_id, created_at: new Date().toISOString() });
    } catch (e) {
      setFailure(e instanceof ApiError && e.status === 422 ? `${e.message} Press Retry to record again.` : describe(e, "saving the recording"));
      setBusy(false);
    }
  };

  return (
    <>
      <p className={styles.help}>
        {isGlassesUser(person)
          ? `A clear recording of ${person.name} is how the glasses tell their own voice from a visitor's. Read a few sentences at a normal pace.`
          : `Read a few sentences at a normal pace, as if talking to the glasses user. The glasses match a voice in the room against these.`}
      </p>
      <Recorder recorder={recorder} />
      <div className={styles.actions}>
        <Button variant="secondary" icon="rotate-ccw" disabled={!recorder.canRetry || busy} onClick={recorder.retry}>
          Retry
        </Button>
        <Button icon="upload" busy={busy} disabled={!recorder.ready} onClick={save}>
          {busy ? "Saving…" : "Save recording"}
        </Button>
      </div>
      {failure && <Notice>{failure}</Notice>}
    </>
  );
}

export function VoiceSection({ person, samples, setSamples, onPerson }: VoiceSectionProps) {
  const [take, setTake] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const refreshPerson = async () => {
    try {
      onPerson(await getPerson(person.id)); // has_voice may have changed
    } catch {
      // the list is already right; the header catches up on the next load
    }
  };

  const remove = async (sample: VoiceSample) => {
    setBusy(sample.voice_sample_id);
    setFailure(null);
    try {
      await deleteVoice(person.id, sample.voice_sample_id);
      setSamples((list) => list.filter((s) => s.voice_sample_id !== sample.voice_sample_id));
      await refreshPerson();
    } catch (e) {
      setFailure(describe(e, "deleting the recording"));
    }
    setBusy(null);
  };

  return (
    <Section title="Voice" aside={<span className={styles.help}>{samples.length === 1 ? "1 recording" : `${samples.length} recordings`}</span>}>
      {samples.length === 0 ? (
        <p className={styles.empty}>No recording yet, so the glasses can't recognize {person.name} by voice.</p>
      ) : (
        <ul className={styles.samples}>
          {samples.map((sample, i) => (
            <li key={sample.voice_sample_id} className={styles.sample}>
              <span className={styles.sampleMeta}>
                Recording {i + 1} · {shortDate(sample.created_at)}
              </span>
              <audio controls preload="none" src={voiceAudioUrl(person.id, sample.voice_sample_id)} aria-label={`Recording ${i + 1} of ${person.name}`} />
              <button
                type="button"
                className={`${styles.iconButton} ${styles.iconDanger}`}
                aria-label={`Delete recording ${i + 1}`}
                disabled={busy !== null}
                onClick={() => remove(sample)}
              >
                <Icon name="trash-2" size={18} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {failure && <Notice>{failure}</Notice>}
      <NewRecording
        key={take}
        person={person}
        onSaved={(sample) => {
          setSamples((list) => [...list, sample]);
          setTake((n) => n + 1);
          void refreshPerson();
        }}
      />
    </Section>
  );
}

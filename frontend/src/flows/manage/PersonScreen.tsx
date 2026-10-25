// One person: everything the glasses store about them, each part editable in place. Not designed.

import { useCallback, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { deletePerson, getPerson, listFacts, listPeople, listPhotos, listVoice } from "../../api/client";
import type { Fact, Person, PhotoOut, VoiceSample } from "../../api/contract";
import { Button } from "../../components/Button";
import { ActionBar, Notice, PageShell, TitleBlock } from "../../components/PageShell";
import { CardSection } from "./CardSection";
import { DetailsSection } from "./DetailsSection";
import { FactsSection } from "./FactsSection";
import styles from "./manage.module.css";
import { PhotosSection } from "./PhotosSection";
import { describe, isGlassesUser, relationshipLabel, Section, useLoad } from "./shared";
import { VoiceSection } from "./VoiceSection";

interface Record {
  person: Person;
  facts: Fact[];
  photos: PhotoOut[];
  voice: VoiceSample[];
  people: Person[];
}

async function loadRecord(id: number): Promise<Record> {
  const [person, facts, photos, voice, people] = await Promise.all([getPerson(id), listFacts(id), listPhotos(), listVoice(id), listPeople()]);
  return { person, facts, photos, voice, people };
}

function RemoveSection({ person, onRemoved }: { person: Person; onRemoved: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await deletePerson(person.id);
      onRemoved();
    } catch (e) {
      setFailure(describe(e, "removing them"));
      setBusy(false);
    }
  };

  return (
    <Section title="Remove">
      <p className={styles.help}>
        Removing {person.name} deletes their voice recordings and notes and unlabels their faces (the photos stay, under Faces to label).
        {isGlassesUser(person) && " This is the glasses user: the live view will have nobody to tell voices apart from until someone is set up again."}
      </p>
      <div className={styles.actions}>
        <Button variant="danger" icon="trash-2" onClick={() => setConfirming(true)} disabled={confirming}>
          Remove {person.name}
        </Button>
        {confirming && (
          <Button variant="secondary" icon="x" onClick={() => setConfirming(false)} disabled={busy}>
            Keep them
          </Button>
        )}
      </div>
      {confirming && (
        <Notice tone="info" action={{ label: busy ? "Removing…" : "Yes, remove them", onClick: remove }}>
          This can't be undone. Remove {person.name} from the glasses?
        </Notice>
      )}
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

export function PersonScreen() {
  const { id: raw } = useParams();
  const id = Number(raw);
  const navigate = useNavigate();
  const loaded = useLoad(() => (Number.isInteger(id) && id > 0 ? loadRecord(id) : Promise.reject(new Error("bad id"))), id);
  const record = loaded.data;
  // PageShell refocuses the h1 and scrolls up whenever its title changes; after a rename that
  // would throw the family's cursor away, so the tab title keeps the name the page opened with.
  const opened = useRef<string | null>(null);
  if (record && opened.current === null) opened.current = record.person.name;

  const setPerson = useCallback((person: Person) => loaded.set((r) => ({ ...r, person, people: r.people.map((p) => (p.id === person.id ? person : p)) })), [loaded]);
  const setFacts = useCallback((update: (facts: Fact[]) => Fact[]) => loaded.set((r) => ({ ...r, facts: update(r.facts) })), [loaded]);
  const setVoice = useCallback((update: (voice: VoiceSample[]) => VoiceSample[]) => loaded.set((r) => ({ ...r, voice: update(r.voice) })), [loaded]);

  const title = record ? record.person.name : "Person";
  const lead = useMemo(() => {
    if (!record) return undefined;
    const p = record.person;
    return `${relationshipLabel(p)} · ${p.face_count} face${p.face_count === 1 ? "" : "s"} · ${record.voice.length} recording${record.voice.length === 1 ? "" : "s"} · ${record.facts.length} fact${record.facts.length === 1 ? "" : "s"}`;
  }, [record]);

  if (!Number.isInteger(id) || id <= 0) return <Navigate to="/manage" replace />;
  return (
    <PageShell
      title={opened.current ?? "Person"}
      footer={
        <ActionBar>
          <Button variant="secondary" to="/manage" icon="arrow-left">
            People
          </Button>
        </ActionBar>
      }
    >
      <main className={styles.main}>
        <TitleBlock title={title} lead={lead} />
        {loaded.error && <Notice action={{ label: "Try again", onClick: loaded.reload }}>{loaded.error}</Notice>}
        {loaded.loading && <p className={styles.loading}>Loading…</p>}
        {record && (
          <>
            {/* Keyed on the stored values: a draft restarts from what the server has whenever that changes
                (Claude rewrote the card, a visit added to it), so a stale draft can't be saved over it. */}
            <DetailsSection key={`${record.person.name}|${record.person.relationship}`} person={record.person} onSaved={setPerson} />
            <CardSection key={record.person.small_context} person={record.person} factCount={record.facts.length} onSaved={setPerson} reload={loaded.reload} />
            <FactsSection person={record.person} facts={record.facts} setFacts={setFacts} onPerson={setPerson} />
            <PhotosSection person={record.person} photos={record.photos} people={record.people} reload={loaded.reload} />
            <VoiceSection person={record.person} samples={record.voice} setSamples={setVoice} onPerson={setPerson} />
            <RemoveSection person={record.person} onRemoved={() => navigate("/manage", { replace: true })} />
          </>
        )}
      </main>
    </PageShell>
  );
}

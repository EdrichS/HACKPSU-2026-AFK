// The facts behind the card: the record Gemini reads. Add one as typed, reword or delete one, or
// hand Gemini a paragraph of notes to turn into facts. Not designed.

import { useState } from "react";

import { addFact, addNotes, ApiError, deleteFact, listFacts, updateFact } from "../../api/client";
import { FACT_MAX, type Fact, type Person } from "../../api/contract";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Fields";
import { Icon } from "../../components/Icon";
import { Notice } from "../../components/PageShell";
import styles from "./manage.module.css";
import { describe, Section, shortDate } from "./shared";

interface FactsSectionProps {
  person: Person;
  facts: Fact[];
  setFacts: (update: (facts: Fact[]) => Fact[]) => void;
  onPerson: (person: Person) => void;
}

function FactRow({ person, fact, setFacts }: { person: Person; fact: Fact; setFacts: FactsSectionProps["setFacts"] }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(fact.text);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const save = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setFailure(null);
    try {
      const saved = await updateFact(person.id, fact.id, text.trim());
      setFacts((facts) => facts.map((f) => (f.id === fact.id ? saved : f)));
      setEditing(false);
    } catch (e) {
      setFailure(describe(e, "saving the fact"));
    }
    setBusy(false);
  };

  const remove = async () => {
    setBusy(true);
    setFailure(null);
    try {
      await deleteFact(person.id, fact.id);
      setFacts((facts) => facts.filter((f) => f.id !== fact.id));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setFacts((facts) => facts.filter((f) => f.id !== fact.id));
      else setFailure(describe(e, "deleting the fact"));
      setBusy(false);
    }
  };

  return (
    <li className={styles.fact}>
      {editing ? (
        <div className={styles.factEdit}>
          <TextArea label="Fact" value={text} onChange={setText} maxLength={FACT_MAX} rows={2} />
          <div className={styles.actions}>
            <Button icon="check" busy={busy} disabled={!text.trim()} onClick={save}>
              Save
            </Button>
            <Button
              variant="secondary"
              icon="x"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setText(fact.text);
                setFailure(null);
              }}
            >
              Cancel
            </Button>
          </div>
          {failure && <Notice>{failure}</Notice>}
        </div>
      ) : (
        <>
          <div className={styles.factText}>
            <span>{fact.text}</span>
            <span className={styles.factMeta}>
              <span>{fact.source === "conversation" ? "From a visit" : "From notes"}</span>
              <span aria-hidden="true">·</span>
              <span>{shortDate(fact.created_at)}</span>
            </span>
            {failure && <Notice>{failure}</Notice>}
          </div>
          <button type="button" className={styles.iconButton} aria-label={`Edit: ${fact.text}`} onClick={() => setEditing(true)} disabled={busy}>
            <Icon name="pencil" size={18} />
          </button>
          <button type="button" className={`${styles.iconButton} ${styles.iconDanger}`} aria-label={`Delete: ${fact.text}`} onClick={remove} disabled={busy}>
            <Icon name="trash-2" size={18} />
          </button>
        </>
      )}
    </li>
  );
}

export function FactsSection({ person, facts, setFacts, onPerson }: FactsSectionProps) {
  const [draft, setDraft] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<"fact" | "notes" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const add = async () => {
    if (!draft.trim()) return;
    setBusy("fact");
    setFailure(null);
    setNote(null);
    try {
      const fact = await addFact(person.id, draft.trim());
      setFacts((facts) => [...facts, fact]);
      setDraft("");
    } catch (e) {
      setFailure(describe(e, "adding the fact"));
    }
    setBusy(null);
  };

  const sendNotes = async () => {
    if (!notes.trim()) return;
    setBusy("notes");
    setFailure(null);
    setNote(null);
    try {
      // The notes route answers 200 with the person unchanged when Gemini is off or found nothing,
      // so look at the facts afterwards before telling the family their notes were taken in.
      const updated = await addNotes(person.id, notes.trim());
      const after = await listFacts(person.id);
      const taken = after.length > facts.length || updated.small_context !== person.small_context;
      onPerson(updated);
      setFacts(() => after);
      if (taken) {
        setNotes("");
        setNote(after.length > facts.length ? `Gemini took ${after.length - facts.length} new fact${after.length - facts.length === 1 ? "" : "s"} from the notes and rewrote the card above.` : "Gemini rewrote the card above from the notes.");
      } else {
        setFailure("Gemini stored nothing from those notes (no Gemini key on the server, or nothing new in them). They're still in the box: add the important bits as facts instead.");
      }
    } catch (e) {
      setFailure(describe(e, "sending the notes"));
    }
    setBusy(null);
  };

  return (
    <Section title="Facts" aside={<span className={styles.help}>{facts.length === 1 ? "1 fact" : `${facts.length} facts`}</span>}>
      <p className={styles.help}>
        The record about {person.name}: what visits and notes have taught the glasses. Gemini writes the card from these. Oldest first.
      </p>
      {facts.length === 0 ? (
        <p className={styles.empty}>No facts yet.</p>
      ) : (
        <ul className={styles.facts}>
          {facts.map((fact) => (
            <FactRow key={`${fact.id}:${fact.text}`} person={person} fact={fact} setFacts={setFacts} />
          ))}
        </ul>
      )}
      <TextArea
        label="Add a fact"
        value={draft}
        onChange={setDraft}
        placeholder={`${person.name} moved to Pittsburgh in October 2026.`}
        helper="One short sentence, stored exactly as typed."
        maxLength={FACT_MAX}
        rows={2}
      />
      <div className={styles.actions}>
        <Button icon="plus" busy={busy === "fact"} disabled={!draft.trim() || busy !== null} onClick={add}>
          Add fact
        </Button>
      </div>
      <TextArea
        label="Or give Gemini some notes"
        value={notes}
        onChange={setNotes}
        placeholder="Anything about them: where they live, what they do, what's coming up…"
        helper="Gemini turns the notes into facts and rewrites the card, the same as the sign-up forms do."
        rows={3}
      />
      <div className={styles.actions}>
        <Button variant="secondary" icon="sparkles" busy={busy === "notes"} disabled={!notes.trim() || busy !== null} onClick={sendNotes}>
          Send to Gemini
        </Button>
      </div>
      {note && <Notice tone="info">{note}</Notice>}
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

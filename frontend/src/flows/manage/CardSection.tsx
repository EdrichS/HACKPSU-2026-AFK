// The card: the few lines the glasses show beside the name. Edited by hand, or written again by
// Gemini from the facts. Not designed.

import { useState } from "react";

import { ApiError, rewriteCard, updatePerson } from "../../api/client";
import { CARD_MAX, type Person } from "../../api/contract";
import { Button } from "../../components/Button";
import { TextArea } from "../../components/Fields";
import { Notice } from "../../components/PageShell";
import styles from "./manage.module.css";
import { describe, Section } from "./shared";

interface CardSectionProps {
  person: Person;
  factCount: number;
  onSaved: (person: Person) => void;
  /** A saved card is also stored as a fact: the facts list must be loaded again. */
  reload: () => void;
}

export function CardSection({ person, factCount, onSaved, reload }: CardSectionProps) {
  const [text, setText] = useState(person.small_context);
  const [busy, setBusy] = useState<"save" | "rewrite" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const changed = text.trim() !== person.small_context;

  const save = async () => {
    setBusy("save");
    setFailure(null);
    setNote(null);
    try {
      const saved = await updatePerson(person.id, { small_context: text.trim() });
      onSaved(saved);
      setText(saved.small_context);
      setNote(text.trim() ? "Saved. The card is also kept as a note, so Gemini's next rewrite starts from it." : "Saved: the card is empty.");
      if (text.trim()) reload();
    } catch (e) {
      setFailure(describe(e, "saving the card"));
    }
    setBusy(null);
  };

  const rewrite = async () => {
    setBusy("rewrite");
    setFailure(null);
    setNote(null);
    try {
      const saved = await rewriteCard(person.id);
      onSaved(saved);
      setText(saved.small_context);
      setNote("Gemini wrote the card again from the facts.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) setFailure("Rewriting needs a Gemini key on the server. The card is unchanged; you can still edit it by hand.");
      else if (e instanceof ApiError && e.status === 502) setFailure(e.message);
      else setFailure(describe(e, "rewriting the card"));
    }
    setBusy(null);
  };

  return (
    <Section title="Card" aside={<span className={styles.help}>{text.trim().length} / {CARD_MAX}</span>}>
      <TextArea
        label="Shown beside the name on the glasses"
        value={text}
        onChange={(value) => {
          setText(value);
          setNote(null);
        }}
        placeholder="Last spoke about: the garden · Works as a nurse | Ask about: the new job"
        helper={"Short fragments separated by \" · \", with \"| Ask about:\" for conversation starters. Nothing upsetting: the wearer reads this."}
        maxLength={CARD_MAX}
        rows={3}
      />
      <div className={styles.actions}>
        <Button icon="check" busy={busy === "save"} disabled={!changed || busy !== null} onClick={save}>
          {busy === "save" ? "Saving…" : "Save card"}
        </Button>
        <Button variant="secondary" icon="sparkles" busy={busy === "rewrite"} disabled={busy !== null || factCount === 0} onClick={rewrite}>
          {busy === "rewrite" ? "Writing…" : "Rewrite from the facts"}
        </Button>
      </div>
      {factCount === 0 && <p className={styles.help}>Add a fact below and Gemini can write the card from it.</p>}
      {note && <Notice tone="info">{note}</Notice>}
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

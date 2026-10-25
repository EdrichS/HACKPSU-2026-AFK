// Name and relationship. Not designed.

import { useState } from "react";

import { ApiError, getUser, updatePerson } from "../../api/client";
import { PERSON_NAME_MAX, PERSON_RELATIONSHIP_MAX, type Person } from "../../api/contract";
import { Button } from "../../components/Button";
import { TextField } from "../../components/Fields";
import { Notice } from "../../components/PageShell";
import styles from "./manage.module.css";
import { describe, isGlassesUser, isUserRelationship, Section } from "./shared";

export function DetailsSection({ person, onSaved }: { person: Person; onSaved: (person: Person) => void }) {
  const [name, setName] = useState(person.name);
  const [relationship, setRelationship] = useState(person.relationship);
  const [error, setError] = useState<string | undefined>();
  const [relationshipError, setRelationshipError] = useState<string | undefined>();
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const user = isGlassesUser(person);
  const changed = name.trim() !== person.name || relationship.trim() !== person.relationship;

  const save = async () => {
    if (!name.trim()) {
      setError("Please enter a name.");
      return;
    }
    if (!user && !relationship.trim()) {
      setRelationshipError("Please say how they're related to the glasses user.");
      return;
    }
    setBusy(true);
    setFailure(null);
    setSaved(false);
    try {
      if (!user && isUserRelationship(relationship)) {
        // Only one wearer: the backend takes the first such row, so a second one would be ignored.
        const existing = await getUser();
        if (existing && existing.id !== person.id) {
          setRelationshipError(`${existing.name} is already the glasses user. Rename them instead, or remove them first.`);
          setBusy(false);
          return;
        }
      }
      const patch = user ? { name: name.trim() } : { name: name.trim(), relationship: relationship.trim() };
      onSaved(await updatePerson(person.id, patch));
      setSaved(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setError(e.message);
      else setFailure(describe(e, "saving"));
    }
    setBusy(false);
  };

  return (
    <Section title="Details">
      <div className={styles.inline}>
        <TextField
          label="Name"
          value={name}
          onChange={(value) => {
            setName(value);
            setError(undefined);
            setSaved(false);
          }}
          maxLength={PERSON_NAME_MAX}
          error={error}
        />
        {user ? (
          <div className={styles.field}>
            <span className={styles.label}>Relationship</span>
            <p className={styles.help}>This is the glasses user, the person wearing the glasses. That can't be changed here.</p>
          </div>
        ) : (
          <TextField
            label="Relationship to the glasses user"
            value={relationship}
            onChange={(value) => {
              setRelationship(value);
              setRelationshipError(undefined);
              setSaved(false);
            }}
            maxLength={PERSON_RELATIONSHIP_MAX}
            error={relationshipError}
          />
        )}
        <div className={styles.inlineAction}>
          <Button icon="check" busy={busy} disabled={!changed} onClick={save}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
      {saved && !changed && <Notice tone="info">Saved.</Notice>}
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

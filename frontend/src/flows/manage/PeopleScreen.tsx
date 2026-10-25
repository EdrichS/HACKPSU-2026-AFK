// Everyone the glasses know, and a way to add someone by hand. Not designed: an admin view in
// the style of the flows (see HomePage for the launcher it hangs off).

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError, createPerson, getUser, listPeople, listPhotos, photoImageUrl } from "../../api/client";
import { PERSON_NAME_MAX, PERSON_RELATIONSHIP_MAX, type Person, type PhotoOut } from "../../api/contract";
import { Button } from "../../components/Button";
import { TextField } from "../../components/Fields";
import { Icon } from "../../components/Icon";
import { ActionBar, Notice, PageShell, TitleBlock } from "../../components/PageShell";
import styles from "./manage.module.css";
import { describe, isGlassesUser, isUserRelationship, relationshipLabel, Section, useLoad } from "./shared";

interface Errors {
  name?: string;
  relationship?: string;
}

/** The glasses user first, then everyone else by name. */
function sorted(people: Person[]): Person[] {
  return [...people].sort((a, b) => Number(isGlassesUser(b)) - Number(isGlassesUser(a)) || a.name.localeCompare(b.name));
}

/** One photo showing each person, for the row's thumbnail. */
function firstPhotos(photos: PhotoOut[]): Map<number, number> {
  const out = new Map<number, number>();
  for (const photo of photos) for (const face of photo.faces) if (face.person_id !== null && !out.has(face.person_id)) out.set(face.person_id, photo.photo_id);
  return out;
}

export function PeopleScreen() {
  const navigate = useNavigate();
  const people = useLoad(() => listPeople(), "people");
  const photos = useLoad(() => listPhotos(), "photos");
  const [name, setName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const relationshipRef = useRef<HTMLInputElement>(null);
  const [focusRequest, setFocusRequest] = useState(0);

  useEffect(() => {
    if (focusRequest === 0) return;
    (errors.name ? nameRef : errors.relationship ? relationshipRef : null)?.current?.focus();
    // Only when asked: re-running as errors clear would move the focus while the family types.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest]);

  const thumbnails = useMemo(() => firstPhotos(photos.data ?? []), [photos.data]);
  const unlabelled = useMemo(() => (photos.data ?? []).reduce((n, p) => n + p.faces.filter((f) => f.person_id === null).length, 0), [photos.data]);

  const add = async () => {
    const found: Errors = {};
    if (!name.trim()) found.name = "Please enter a name.";
    if (!relationship.trim()) found.relationship = "Please say how they're related to the glasses user, or 'user' for the wearer.";
    setErrors(found);
    if (found.name || found.relationship) {
      setFocusRequest((n) => n + 1);
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      if (isUserRelationship(relationship)) {
        const existing = await getUser(); // only one wearer: the backend takes the first such row
        if (existing) {
          setErrors({ relationship: `${existing.name} is already the glasses user. Open them to rename, or remove them first.` });
          setFocusRequest((n) => n + 1);
          setBusy(false);
          return;
        }
      }
      const person = await createPerson({ name: name.trim(), relationship: relationship.trim() });
      navigate(`/manage/people/${person.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setErrors({ name: e.message });
        setFocusRequest((n) => n + 1);
      } else setFailure(describe(e, "adding them"));
      setBusy(false);
    }
  };

  return (
    <PageShell
      title="People"
      footer={
        <ActionBar>
          <Button variant="secondary" to="/" icon="arrow-left">
            Home
          </Button>
          <Button variant="secondary" to="/manage/faces" icon="scan-face">
            {unlabelled > 0 ? `Label ${unlabelled} face${unlabelled === 1 ? "" : "s"}` : "Faces to label"}
          </Button>
        </ActionBar>
      }
    >
      <main className={styles.main}>
        <TitleBlock title="People" lead="Everyone the glasses know, with their photos, voice and notes. Open someone to change what the glasses show about them." />

        {people.error && <Notice action={{ label: "Try again", onClick: people.reload }}>{people.error}</Notice>}
        {people.loading && <p className={styles.loading}>Loading…</p>}
        {people.data && people.data.length === 0 && <p className={styles.empty}>Nobody yet. Add someone below, or share the visitor sign-up link.</p>}
        {people.data && people.data.length > 0 && (
          <ul className={styles.list}>
            {sorted(people.data).map((person) => {
              const photoId = thumbnails.get(person.id);
              return (
                <li key={person.id}>
                  <Link to={`/manage/people/${person.id}`} className={styles.row}>
                    <span className={styles.avatar} aria-hidden="true">
                      {photoId !== undefined ? <img src={photoImageUrl(photoId)} alt="" loading="lazy" /> : <Icon name="user" size={22} />}
                    </span>
                    <span className={styles.rowText}>
                      <span className={styles.rowTitle}>
                        {person.name}
                        <span className={isGlassesUser(person) ? `${styles.pill} ${styles.pillAccent}` : styles.pill}>{relationshipLabel(person)}</span>
                      </span>
                      <span className={styles.rowMeta}>
                        {person.face_count} face{person.face_count === 1 ? "" : "s"} · {person.has_voice ? "voice recorded" : "no voice yet"} ·{" "}
                        {person.small_context ? person.small_context : "no card yet"}
                      </span>
                    </span>
                    <Icon name="arrow-right" size={18} />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}

        <Section title="Add someone">
          <p className={styles.help}>
            A person added here has no photos or voice yet; add them on their page. The wearer is the one with the relationship "user".
          </p>
          <div className={styles.inline}>
            <TextField
              label="Name"
              value={name}
              onChange={(value) => {
                setName(value);
                setErrors((previous) => ({ ...previous, name: undefined }));
              }}
              placeholder="e.g. Maya"
              maxLength={PERSON_NAME_MAX}
              error={errors.name}
              inputRef={nameRef}
            />
            <TextField
              label="Relationship to the glasses user"
              value={relationship}
              onChange={(value) => {
                setRelationship(value);
                setErrors((previous) => ({ ...previous, relationship: undefined }));
              }}
              placeholder="e.g. granddaughter"
              maxLength={PERSON_RELATIONSHIP_MAX}
              error={errors.relationship}
              inputRef={relationshipRef}
            />
            <div className={styles.inlineAction}>
              <Button icon="plus" busy={busy} onClick={add}>
                {busy ? "Adding…" : "Add"}
              </Button>
            </div>
          </div>
          {failure && <Notice>{failure}</Notice>}
        </Section>
      </main>
    </PageShell>
  );
}

// Faces found in photos that nobody has been matched to: label them, or throw the photo away.
// Not designed.

import { useMemo, useState } from "react";

import { assignFace, deletePhoto, listPeople, listPhotos } from "../../api/client";
import type { Person, PhotoOut } from "../../api/contract";
import { Button } from "../../components/Button";
import { ActionBar, Notice, PageShell, TitleBlock } from "../../components/PageShell";
import styles from "./manage.module.css";
import { PhotoTile } from "./PhotoTile";
import { describe, relationshipLabel, Section, useLoad } from "./shared";

function unlabelled(photos: PhotoOut[]): PhotoOut[] {
  return photos.filter((photo) => photo.faces.some((face) => face.person_id === null));
}

function FaceRow({ photo, people, onDone }: { photo: PhotoOut; people: Person[]; onDone: () => void }) {
  const faces = photo.faces.filter((face) => face.person_id === null);
  const [choice, setChoice] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const run = async (doing: string, work: () => Promise<void>) => {
    setBusy(true);
    setFailure(null);
    try {
      await work();
      onDone();
    } catch (e) {
      setFailure(describe(e, doing));
    }
    setBusy(false); // the row stays mounted while the photo has other faces to label
  };
  // A person can be on one face per photo: whoever is already labelled here can't be this face.
  const labelled = new Set(photo.faces.map((face) => face.person_id));
  const candidates = people.filter((person) => !labelled.has(person.id));

  return (
    <Section title={`Photo ${photo.photo_id}`} aside={<span className={styles.help}>{faces.length === 1 ? "1 face to label" : `${faces.length} faces to label`}</span>}>
      <ul className={styles.photos} style={{ gridTemplateColumns: "minmax(0, 320px)" }}>
        <PhotoTile photo={photo} people={people} fit />
      </ul>
      {faces.map((face, i) => (
        <div key={face.face_id} className={styles.inline}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={`face-${face.face_id}`}>
              {faces.length === 1 ? "Who is this?" : `Face ${i + 1} (from the left: ${[...faces].sort((a, b) => a.box.x - b.box.x).indexOf(face) + 1}) is`}
            </label>
            <select id={`face-${face.face_id}`} className={styles.select} value={choice[face.face_id] ?? ""} onChange={(e) => setChoice({ ...choice, [face.face_id]: e.target.value })}>
              <option value="">Choose a person…</option>
              {candidates.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name} · {relationshipLabel(person)}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.inlineAction}>
            <Button
              icon="check"
              busy={busy}
              disabled={!choice[face.face_id]}
              onClick={() => run("labelling the face", () => assignFace(face.face_id, Number(choice[face.face_id])))}
            >
              Label
            </Button>
          </div>
        </div>
      ))}
      <div className={styles.actions}>
        <Button variant="danger" icon="trash-2" busy={busy} onClick={() => run("deleting the photo", () => deletePhoto(photo.photo_id))}>
          Delete photo
        </Button>
      </div>
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

export function FacesScreen() {
  const loaded = useLoad(() => Promise.all([listPhotos(), listPeople()]), "faces");
  const photos = useMemo(() => (loaded.data ? unlabelled(loaded.data[0]) : []), [loaded.data]);
  const people = loaded.data?.[1] ?? [];

  return (
    <PageShell
      title="Faces to label"
      footer={
        <ActionBar>
          <Button variant="secondary" to="/manage" icon="arrow-left">
            People
          </Button>
        </ActionBar>
      }
    >
      <main className={styles.main}>
        <TitleBlock
          title="Faces to label"
          lead="Photos where a face was found that isn't matched to anyone: someone in the background of a sign-up, or a sign-up that stopped halfway. Label the face, or delete the photo."
        />
        {loaded.error && <Notice action={{ label: "Try again", onClick: loaded.reload }}>{loaded.error}</Notice>}
        {loaded.loading && <p className={styles.loading}>Loading…</p>}
        {loaded.data && photos.length === 0 && <p className={styles.empty}>Every face is labelled.</p>}
        {photos.map((photo) => (
          <FaceRow key={photo.photo_id} photo={photo} people={people} onDone={loaded.reload} />
        ))}
      </main>
    </PageShell>
  );
}

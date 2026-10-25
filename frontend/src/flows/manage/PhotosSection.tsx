// The photos this person's faces were found in. Add one (the biggest clear face in it becomes
// theirs), unlabel their face, or delete the photo. Not designed.

import { useMemo, useRef, useState } from "react";

import { assignFace, deletePhoto, uploadPhoto } from "../../api/client";
import type { Person, PhotoOut } from "../../api/contract";
import { dominant } from "../../api/visitor";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icon";
import { Notice } from "../../components/PageShell";
import styles from "./manage.module.css";
import { PhotoTile } from "./PhotoTile";
import { describe, Section } from "./shared";

interface PhotosSectionProps {
  person: Person;
  photos: PhotoOut[];
  people: Person[];
  reload: () => void;
}

export function PhotosSection({ person, photos, people, reload }: PhotosSectionProps) {
  const mine = useMemo(() => photos.filter((photo) => photo.faces.some((face) => face.person_id === person.id)), [photos, person.id]);
  const [busy, setBusy] = useState<number | "upload" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async (key: number | "upload", doing: string, work: () => Promise<string | null>) => {
    setBusy(key);
    setFailure(null);
    setNote(null);
    try {
      const message = await work();
      if (message) setNote(message);
      reload();
    } catch (e) {
      setFailure(describe(e, doing));
    }
    setBusy(null);
  };

  const upload = (file: File | undefined) => {
    if (!file) return;
    void run("upload", "adding the photo", async () => {
      const out = await uploadPhoto(file, file.name || "photo.jpg");
      const face = dominant(out.faces);
      if (!face) {
        await deletePhoto(out.photo_id);
        return out.faces.length === 0 ? "No face was found in that photo, so it wasn't kept." : "Two faces of a similar size: the photo wasn't kept. Use one where the person is clearly the biggest face.";
      }
      try {
        await assignFace(face.face_id, person.id);
      } catch (e) {
        await deletePhoto(out.photo_id).catch(() => undefined); // not left behind as a nameless face
        throw e;
      }
      return null;
    });
  };

  return (
    <Section
      title="Photos"
      aside={
        <>
          <input
            ref={fileRef}
            className={styles.fileInput}
            type="file"
            accept="image/jpeg,image/png"
            onChange={(e) => {
              upload(e.target.files?.[0]);
              e.target.value = "";
            }}
            tabIndex={-1}
            aria-hidden="true"
          />
          <Button variant="secondary" icon="upload" busy={busy === "upload"} disabled={busy !== null} onClick={() => fileRef.current?.click()}>
            Add photo
          </Button>
        </>
      }
    >
      <p className={styles.help}>
        {person.face_count === 0
          ? `No face is labelled as ${person.name} yet, so the glasses can't recognize them by sight. Add a photo where they are the biggest face.`
          : `${person.face_count} labelled face${person.face_count === 1 ? "" : "s"}. The glasses match a face in view against these.`}
      </p>
      {mine.length > 0 && (
        <ul className={styles.photos}>
          {mine.map((photo) => {
            const face = photo.faces.find((f) => f.person_id === person.id);
            return (
              <PhotoTile
                key={photo.photo_id}
                photo={photo}
                people={people}
                fit
                actions={
                  <>
                    {face && (
                      <button
                        type="button"
                        className={styles.iconButton}
                        aria-label={`Unlabel ${person.name} in photo ${photo.photo_id}`}
                        title="Not them: unlabel this face"
                        disabled={busy !== null}
                        onClick={() => run(photo.photo_id, "unlabelling the face", async () => (await assignFace(face.face_id, null), null))}
                      >
                        <Icon name="x" size={18} />
                      </button>
                    )}
                    <button
                      type="button"
                      className={`${styles.iconButton} ${styles.iconDanger}`}
                      aria-label={`Delete photo ${photo.photo_id}`}
                      title="Delete this photo"
                      disabled={busy !== null}
                      onClick={() => run(photo.photo_id, "deleting the photo", async () => (await deletePhoto(photo.photo_id), null))}
                    >
                      <Icon name="trash-2" size={18} />
                    </button>
                  </>
                }
              />
            );
          })}
        </ul>
      )}
      {note && <Notice tone="info">{note}</Notice>}
      {failure && <Notice>{failure}</Notice>}
    </Section>
  );
}

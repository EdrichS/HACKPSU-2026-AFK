// A stored photo with its faces drawn over it, as the manage pages show photos. Not designed.

import { useMemo, type ReactNode } from "react";

import { photoImageUrl } from "../../api/client";
import type { Person, PhotoOut } from "../../api/contract";
import styles from "./manage.module.css";

interface PhotoTileProps {
  photo: PhotoOut;
  /** For the labels on the boxes. */
  people: readonly Person[];
  /** Fit the whole photo (boxes line up) rather than cropping it square. */
  fit?: boolean;
  actions?: ReactNode;
}

export function PhotoTile({ photo, people, fit, actions }: PhotoTileProps) {
  const names = useMemo(() => new Map(people.map((p) => [p.id, p.name])), [people]);
  return (
    <li className={styles.photo}>
      <div className={fit ? `${styles.frame} ${styles.frameFit}` : styles.frame}>
        <img src={photoImageUrl(photo.photo_id)} alt={`Photo ${photo.photo_id}`} width={photo.width} height={photo.height} loading="lazy" />
        {fit &&
          photo.faces.map((face) => {
            const name = face.person_id === null ? null : (names.get(face.person_id) ?? `Person ${face.person_id}`);
            return (
              <div
                key={face.face_id}
                className={name === null ? `${styles.box} ${styles.boxUnlabelled}` : styles.box}
                style={{
                  left: `${(face.box.x / photo.width) * 100}%`,
                  top: `${(face.box.y / photo.height) * 100}%`,
                  width: `${(face.box.width / photo.width) * 100}%`,
                  height: `${(face.box.height / photo.height) * 100}%`,
                }}
                aria-hidden="true"
              >
                <span className={styles.boxLabel}>{name ?? "Unlabelled"}</span>
              </div>
            );
          })}
      </div>
      {actions && <div className={styles.photoActions}>{actions}</div>}
    </li>
  );
}

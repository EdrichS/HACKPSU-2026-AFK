import { memo, useMemo } from "react";

import type { PresentPerson } from "../api/contract";
import styles from "./InfoPanel.module.css";
import { toBullets } from "./people";

/** The liquid glass card about the person in view. Undesigned: hidden with no one, or no notes. */
export const InfoPanel = memo(function InfoPanel({ person }: { person: PresentPerson | null }) {
  const bullets = useMemo(() => (person ? toBullets(person.small_context) : []), [person]);
  if (!person || bullets.length === 0) return null;
  return (
    <aside className={styles.panel} aria-label={`About ${person.name}`}>
      <div className={styles.sheen} aria-hidden="true" />
      <h2 className={styles.name}>{person.name}</h2>
      <div className={styles.divider} aria-hidden="true" />
      <ul className={styles.bullets}>
        {bullets.map((bullet, i) => (
          <li key={i} className={styles.bullet}>
            <span className={styles.square} aria-hidden="true" />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
});

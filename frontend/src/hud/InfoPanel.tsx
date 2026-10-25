import { memo, useMemo } from "react";

import type { PresentPerson } from "../api/contract";
import styles from "./InfoPanel.module.css";
import { parseCard } from "./people";

/**
 * The liquid glass card about the person in view: their card (small_context), set in three parts
 * (the latest conversation, the standing context, what to ask about) in large type so it reads at
 * a glance. Undesigned beyond the glass itself: hidden with no one, or no card yet.
 */
export const InfoPanel = memo(function InfoPanel({ person }: { person: PresentPerson | null }) {
  const card = useMemo(() => (person ? parseCard(person.small_context) : null), [person]);
  if (!person || !card || (!card.recent && card.about.length === 0 && !card.ask)) return null;
  return (
    <aside className={styles.panel} aria-label={`About ${person.name}`}>
      <div className={styles.sheen} aria-hidden="true" />
      <h2 className={styles.name}>{person.name}</h2>
      <div className={styles.divider} aria-hidden="true" />
      {card.recent && (
        <section className={styles.section}>
          <h3 className={styles.label}>Last spoke about</h3>
          <p className={styles.text}>{card.recent}</p>
        </section>
      )}
      {card.about.length > 0 && (
        <section className={styles.section}>
          <h3 className={styles.label}>About {person.name}</h3>
          <p className={styles.text}>{card.about.join("  ·  ")}</p>
        </section>
      )}
      {card.ask && (
        <section className={`${styles.section} ${styles.ask}`}>
          <h3 className={styles.label}>Ask about</h3>
          <p className={`${styles.text} ${styles.askText}`}>{card.ask}</p>
        </section>
      )}
    </aside>
  );
});

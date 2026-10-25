import { Icon } from "./Icon";
import styles from "./PhotoStrip.module.css";

export interface Shot {
  id: string;
  label: string;
  /** The photo, or null while it hasn't been taken. */
  url: string | null;
}

interface PhotoStripProps {
  shots: readonly Shot[];
  /** The shot being taken right now, outlined. */
  active?: string | null;
}

/** One tile per shot: a round thumbnail with a check badge once it's taken, and its label. */
export function PhotoStrip({ shots, active }: PhotoStripProps) {
  return (
    <ul aria-label="Captured photos" className={styles.strip}>
      {shots.map((shot) => {
        const current = shot.id === active;
        return (
          <li key={shot.id} className={current ? `${styles.tile} ${styles.current}` : styles.tile}>
            <span className={styles.thumb}>
              {shot.url ? (
                <>
                  <span className={styles.circle}>
                    {/* Mirrored to match the preview the visitor saw; the uploaded photo isn't. */}
                    <img src={shot.url} alt="" className={styles.image} />
                  </span>
                  <span className={styles.badge} aria-hidden="true">
                    <Icon name="check" size={9} strokeWidth={4} />
                  </span>
                </>
              ) : (
                <span className={`${styles.circle} ${styles.empty}`} />
              )}
            </span>
            <span className={styles.label}>{shot.label}</span>
            <span className="visually-hidden">, {shot.url ? "taken" : current ? "being taken" : "not taken yet"}</span>
          </li>
        );
      })}
    </ul>
  );
}

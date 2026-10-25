import { memo } from "react";

import { Icon } from "../components/Icon";
import type { CaptionLine } from "./captions";
import styles from "./Captions.module.css";

/** The word still being transcribed is dimmed and followed by a blinking cursor. */
function PendingText({ text }: { text: string }) {
  const trimmed = text.trimEnd();
  const cut = trimmed.lastIndexOf(" ") + 1;
  return (
    <>
      {trimmed.slice(0, cut)}
      <span className={styles.pending}>{trimmed.slice(cut)}</span>
      <span className={styles.cursor} aria-hidden="true" />
    </>
  );
}

/**
 * The caption bar. The live region stays mounted while empty (just invisible) so screen readers
 * announce the next line; undesigned: it hides when there is nothing to show.
 */
export const Captions = memo(function Captions({ line }: { line: CaptionLine | null }) {
  return (
    <section
      aria-label="Live captions"
      aria-live="polite"
      className={line ? styles.bar : `${styles.bar} ${styles.empty}`}
    >
      {line && (
        <>
          <div className={styles.speaker}>
            <Icon name="audio-lines" size={18} />
            <span>{line.speaker}</span>
          </div>
          <p className={styles.text}>{line.final ? line.text : <PendingText text={line.text} />}</p>
        </>
      )}
    </section>
  );
});

// The HUD's two buttons. Neither is designed; both wear the live pill's glass.

import styles from "./Controls.module.css";
import pill from "./Pill.module.css";

/** Browsers need a click before speech and before the camera and mic prompts. */
export function StartButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className={`${pill.glass} ${styles.button} ${styles.start}`} onClick={onClick}>
      Start live view
    </button>
  );
}

/**
 * Asks the server who is in view; the answer is spoken and captioned. Space does the same.
 * It replaces Start under the same click, so it takes the focus; aria-disabled (not disabled)
 * keeps it focusable while the socket connects.
 */
export function WhoButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      className={`${pill.glass} ${styles.button} ${styles.who}`}
      onClick={disabled ? undefined : onClick}
      aria-disabled={disabled || undefined}
      aria-keyshortcuts="Space"
      autoFocus
    >
      Who is this?
    </button>
  );
}

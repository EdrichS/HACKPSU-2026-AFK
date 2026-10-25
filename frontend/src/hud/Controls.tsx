// The HUD's Start button and its way home. Neither is designed; both wear the live pill's glass.
// There is no on-screen "Who is this?": the wearer asks Nova, or presses Space.

import { Link } from "react-router";

import styles from "./Controls.module.css";
import pill from "./Pill.module.css";

/** Back to the launcher. Top right, above the info panel. */
export function HomeLink() {
  return (
    <Link to="/" className={`${pill.glass} ${styles.button} ${styles.home}`}>
      Home
    </Link>
  );
}

/** Browsers need a click before speech and before the camera and mic prompts. */
export function StartButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className={`${pill.glass} ${styles.button} ${styles.start}`} onClick={onClick}>
      Start live view
    </button>
  );
}

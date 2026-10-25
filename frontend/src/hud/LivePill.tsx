import { memo } from "react";

import { Icon, type IconName } from "../components/Icon";
import styles from "./LivePill.module.css";
import pill from "./Pill.module.css";

/** Undesigned: a feature that is off (refused, muted, no source yet) is dimmed to 45%. */
function Feature({ icon, label, on }: { icon: IconName; label: string; on: boolean }) {
  return (
    <div className={on ? styles.feature : `${styles.feature} ${styles.off}`}>
      <Icon name={icon} size={18} />
      <span>{label}</span>
      {!on && <span className="visually-hidden"> (off)</span>}
    </div>
  );
}

interface LivePillProps {
  connected: boolean;
  face: boolean;
  voice: boolean;
  captions: boolean;
}

/** Live status. Undesigned: until the socket is open the dot is grey and still, and reads CONNECTING. */
export const LivePill = memo(function LivePill({ connected, face, voice, captions }: LivePillProps) {
  return (
    <div className={`${pill.glass} ${styles.pill}`}>
      <div className={styles.status}>
        <span className={connected ? styles.dot : `${styles.dot} ${styles.dotIdle}`} aria-hidden="true" />
        <span role="status">{connected ? "LIVE" : "CONNECTING"}</span>
      </div>
      <span className={styles.divider} aria-hidden="true" />
      <Feature icon="scan-face" label="Face" on={face} />
      <Feature icon="mic" label="Voice" on={voice} />
      <Feature icon="captions" label="Captions" on={captions} />
    </div>
  );
});

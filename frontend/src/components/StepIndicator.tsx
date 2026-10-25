import styles from "./StepIndicator.module.css";

interface StepIndicatorProps {
  current: number;
  total: number;
}

/** "Step 2 of 4" is read aloud; the segments are decorative. */
export function StepIndicator({ current, total }: StepIndicatorProps) {
  return (
    <div className={styles.indicator}>
      <span className={styles.label}>
        Step {current} of {total}
      </span>
      <div className={styles.segments} aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={i < current ? styles.done : styles.todo} />
        ))}
      </div>
    </div>
  );
}

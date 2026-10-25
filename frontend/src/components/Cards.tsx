import styles from "./Cards.module.css";

/** The paragraph a person reads out loud while the Recorder runs. */
export function VoicePrompt({ text }: { text: string }) {
  return (
    <div className={styles.prompt}>
      <p className={styles.promptText}>{text}</p>
    </div>
  );
}

/** The visitor's first name in Pixelify, above their photo on Thank you. */
export function NameTag({ name }: { name: string }) {
  return <span className={styles.nameTag}>{name}</span>;
}

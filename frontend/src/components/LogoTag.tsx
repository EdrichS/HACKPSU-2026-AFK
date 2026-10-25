import styles from "./LogoTag.module.css";

interface LogoTagProps {
  size?: "sm" | "xl";
}

/** "Name Tags" in Pixelify on `tag-bg`. `xl` is the Intro title, so it is the page's h1. */
export function LogoTag({ size = "sm" }: LogoTagProps) {
  if (size === "xl")
    return (
      <h1 className={styles.xl} tabIndex={-1}>
        Name Tags
      </h1>
    );
  return <span className={styles.sm}>Name Tags</span>;
}

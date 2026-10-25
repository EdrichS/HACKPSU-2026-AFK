import { Link } from "react-router";

import styles from "./LogoTag.module.css";

interface LogoTagProps {
  size?: "sm" | "xl";
  /** Where the small tag links to (the page header's way home). Undesigned: the mockups' tag is static. */
  to?: string;
}

/** "Name Tags" in Pixelify on `tag-bg`. `xl` is the Intro title, so it is the page's h1. */
export function LogoTag({ size = "sm", to }: LogoTagProps) {
  if (size === "xl")
    return (
      <h1 className={styles.xl} tabIndex={-1}>
        Name Tags
      </h1>
    );
  if (to)
    return (
      <Link to={to} className={styles.sm} aria-label="Name Tags home">
        Name Tags
      </Link>
    );
  return <span className={styles.sm}>Name Tags</span>;
}

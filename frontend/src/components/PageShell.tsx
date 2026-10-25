import { useEffect, useRef, type ReactNode } from "react";

import { LogoTag } from "./LogoTag";
import styles from "./PageShell.module.css";
import { StepIndicator } from "./StepIndicator";

interface PageShellProps {
  /** The browser tab title: "Name Tags · Consent". */
  title: string;
  /** Header with the logo. Intro has none. */
  header?: boolean;
  step?: { current: number; total: number };
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * Full-height column: header (logo left, step indicator right), main (fills the space, content
 * centered vertically), footer (actions pinned to the bottom). Screens render their own <main>.
 */
export function PageShell({ title, header = true, step, footer, children }: PageShellProps) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = `Name Tags · ${title}`;
    // A new step is a new page to a screen reader: start reading from its title, not the old focus.
    root.current?.querySelector<HTMLElement>("h1")?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [title]);

  return (
    <div className={styles.page} ref={root}>
      {header && (
        <header className={step ? styles.header : `${styles.header} ${styles.headerLogoOnly}`}>
          <LogoTag to="/" />
          {step && <StepIndicator current={step.current} total={step.total} />}
        </header>
      )}
      {children}
      {footer}
    </div>
  );
}

interface FormMainProps {
  /** 640 forms, 720 Consent, 780 Voice. */
  width: 640 | 720 | 780;
  /** Form screens cap the gap between blocks at 26px instead of 28px. */
  form?: boolean;
  children: ReactNode;
}

export function FormMain({ width, form, children }: FormMainProps) {
  return (
    <main className={form ? `${styles.formMain} ${styles.formGap}` : styles.formMain} style={{ maxWidth: width }}>
      {children}
    </main>
  );
}

/** Step title and the lead under it. The h1 takes focus on each step, so it is focusable. */
export function TitleBlock({ title, lead }: { title: ReactNode; lead?: ReactNode }) {
  return (
    <div className={styles.titleBlock}>
      <h1 className={styles.title} tabIndex={-1}>
        {title}
      </h1>
      {lead && <p className={styles.lead}>{lead}</p>}
    </div>
  );
}

/** Max 560px, centered; two buttons share the row equally, a single one fills it. */
export function ActionBar({ children, intro }: { children: ReactNode; intro?: boolean }) {
  return (
    <footer className={intro ? `${styles.footer} ${styles.footerIntro}` : styles.footer}>
      <div className={intro ? styles.actionsIntro : styles.actions}>{children}</div>
    </footer>
  );
}

/** "You can now close this website." on the final screens. */
export function FooterNote({ children }: { children: ReactNode }) {
  return (
    <footer className={styles.footer}>
      <p className={styles.note}>{children}</p>
    </footer>
  );
}

interface NoticeProps {
  children: ReactNode;
  tone?: "error" | "info";
  /** False when the notice sits inside a live region that's already mounted. */
  live?: boolean;
  /** A way to recover, shown as a 44px-tall text button after the message. */
  action?: { label: string; onClick: () => void };
}

/** Undesigned: an error or notice above the actions (upload failed, offline, mic blocked). */
export function Notice({ children, tone = "error", live = true, action }: NoticeProps) {
  const role = live ? (tone === "error" ? "alert" : "status") : undefined;
  return (
    <div className={tone === "error" ? `${styles.notice} ${styles.noticeError}` : styles.notice} role={role}>
      <p className={styles.noticeText}>{children}</p>
      {action && (
        <button type="button" className={`link-button ${styles.noticeAction}`} onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}

export { styles as layoutStyles };

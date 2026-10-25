import { Link } from "react-router";

import { FooterNote, PageShell } from "../../components/PageShell";
import { Icon } from "../../components/Icon";
import styles from "./glasses-user.module.css";
import { useGlassesUserFlow } from "./state";

export function AllSetScreen() {
  const { doneName } = useGlassesUserFlow();
  return (
    <PageShell title="All set" footer={
        <FooterNote>
          You can now close this website, or <Link to="/">go back to the start</Link>.
        </FooterNote>
      }>
      <main className={styles.doneMain}>
        <span className={styles.badge} aria-hidden="true">
          <Icon name="check" strokeWidth={2.5} className={styles.badgeIcon} />
        </span>
        <h1 className={styles.doneTitle} tabIndex={-1}>
          You're all set, {doneName}.
        </h1>
        <p className={styles.doneLead}>Your glasses are ready. Name tags will show up as your family and friends sign up.</p>
      </main>
    </PageShell>
  );
}

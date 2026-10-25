import { useEffect } from "react";

import { NameTag } from "../../components/Cards";
import { Link } from "react-router";

import { FooterNote, PageShell } from "../../components/PageShell";
import styles from "./visitor.module.css";
import { useVisitorFlow } from "./state";

export function ThankYouScreen() {
  const { glassesUserName, submitted, reset } = useVisitorFlow();
  // Everything is uploaded: drop the photos and the recording from memory.
  useEffect(reset, [reset]);
  return (
    <PageShell
      title="Thank you"
      footer={
        <FooterNote>
          You can now close this website, or <Link to="/">go back to the start</Link>.
        </FooterNote>
      }
    >
      <main className={styles.finalMain}>
        <h1 className={styles.finalTitle} tabIndex={-1}>
          Thank you for helping {glassesUserName}.
        </h1>
        <figure className={styles.figure}>
          <NameTag name={submitted?.name ?? ""} />
          <div className={styles.photo}>{submitted?.photoUrl && <img src={submitted.photoUrl} alt="Your photo" />}</div>
        </figure>
      </main>
    </PageShell>
  );
}

import { Button } from "../../components/Button";
import { LogoTag } from "../../components/LogoTag";
import { ActionBar, PageShell } from "../../components/PageShell";
import styles from "./visitor.module.css";
import { useVisitorFlow } from "./state";

export function IntroScreen() {
  const { glassesUserName } = useVisitorFlow();
  return (
    <PageShell
      title="Intro"
      header={false}
      footer={
        <ActionBar intro>
          <Button to="/visitor/consent" intro icon="arrow-right" iconAfter>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <main className={styles.introMain}>
        <LogoTag size="xl" />
        <p className={styles.display}>
          Help <span className={styles.highlight}>{glassesUserName}</span> remember you.
        </p>
      </main>
    </PageShell>
  );
}

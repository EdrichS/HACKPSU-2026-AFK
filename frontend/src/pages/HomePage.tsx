import { useEffect } from "react";
import { Link } from "react-router";

import { LogoTag } from "../components/LogoTag";
import styles from "./HomePage.module.css";

/** Not a designed screen: a launcher in the style of Design/screens/index.html. */
export function HomePage() {
  useEffect(() => {
    document.title = "Name Tags";
  }, []);
  return (
    <main className={styles.main}>
      <LogoTag />
      <p className={styles.intro}>
        Name Tags shows the glasses user who they're talking to. Visitors sign up once with a few photos and a short
        recording; the glasses then show their name, relationship and a few notes.
      </p>
      <h2 className={styles.heading}>Glasses live view</h2>
      <ol className={styles.list}>
        <li>
          <Link to="/live">Live view</Link>
        </li>
      </ol>
      <h2 className={styles.heading}>Visitor sign up</h2>
      <ol className={styles.list}>
        <li>
          <Link to="/visitor">Sign up as a visitor</Link>
        </li>
      </ol>
      <p className={styles.hint}>
        Share <code>/visitor?for=Rose</code> to greet visitors with the glasses user's name.
      </p>
      <h2 className={styles.heading}>Glasses user setup</h2>
      <ol className={styles.list}>
        <li>
          <Link to="/setup">Set up the glasses user</Link>
        </li>
      </ol>
    </main>
  );
}

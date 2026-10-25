import type { ReactNode } from "react";

import styles from "./Consent.module.css";
import { Icon, type IconName } from "./Icon";

export interface ConsentItem {
  icon: IconName;
  title: string;
  body: string;
}

export function ConsentList({ items }: { items: ConsentItem[] }) {
  return (
    <ul className={styles.list}>
      {items.map((item) => (
        <li key={item.title} className={styles.row}>
          <span className={styles.iconTile} aria-hidden="true">
            <Icon name={item.icon} size={22} />
          </span>
          <div className={styles.text}>
            <span className={styles.title}>{item.title}</span>
            <span className={styles.body}>{item.body}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

interface ConsentCheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
}

export function ConsentCheckbox({ checked, onChange, children }: ConsentCheckboxProps) {
  return (
    <label className={styles.checkbox}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className={styles.box} />
      <span>{children}</span>
    </label>
  );
}

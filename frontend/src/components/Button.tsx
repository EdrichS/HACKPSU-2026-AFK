import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";

import styles from "./Button.module.css";
import { Icon, type IconName } from "./Icon";

interface CommonProps {
  /** danger is not designed: the manage pages' delete buttons, a secondary button in --danger. */
  variant?: "primary" | "secondary" | "danger";
  icon?: IconName;
  /** Continue puts its arrow after the label; Retry and Upload put theirs before. */
  iconAfter?: boolean;
  iconSize?: number;
  /** The Intro's larger button: 58px tall, 18px text. */
  intro?: boolean;
  /** Shows a spinner in place of the icon and blocks clicks (Uploading). */
  busy?: boolean;
  children: ReactNode;
}

type LinkProps = CommonProps & { to: string; replace?: boolean };
type NativeProps = CommonProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & { to?: undefined };

function classes({ variant = "primary", intro }: CommonProps) {
  const look = variant === "primary" ? styles.primary : variant === "danger" ? `${styles.secondary} ${styles.danger}` : styles.secondary;
  return [styles.button, look, intro && styles.intro]
    .filter(Boolean)
    .join(" ");
}

function Content({ icon, iconAfter, iconSize, busy, children }: CommonProps) {
  const glyph = busy ? (
    <Icon name="loader" size={iconSize ?? 20} className={styles.spinner} />
  ) : icon ? (
    <Icon name={icon} size={iconSize ?? (icon === "rotate-ccw" ? 18 : 20)} />
  ) : null;
  return (
    <>
      {!iconAfter && glyph}
      {children}
      {iconAfter && glyph}
    </>
  );
}

/** A link styled as a button when `to` is given (plain navigation), otherwise a real button. */
export function Button(props: LinkProps | NativeProps) {
  if (props.to !== undefined) {
    const { to, replace, variant, icon, iconAfter, iconSize, intro, busy, children } = props;
    return (
      <Link to={to} replace={replace} className={classes({ variant, intro, children })}>
        <Content icon={icon} iconAfter={iconAfter} iconSize={iconSize} busy={busy}>
          {children}
        </Content>
      </Link>
    );
  }
  const { variant, icon, iconAfter, iconSize, intro, busy, children, type = "button", disabled, ...rest } = props;
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={classes({ variant, intro, children })}
    >
      <Content icon={icon} iconAfter={iconAfter} iconSize={iconSize} busy={busy}>
        {children}
      </Content>
    </button>
  );
}

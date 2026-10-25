import { useId, type ChangeEvent, type Ref } from "react";

import styles from "./Fields.module.css";
import { Icon } from "./Icon";

/** Inline error under a field. Not designed; the handoff suggests this placement. */
function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <span id={id} className={styles.error} role="alert">
      <Icon name="alert-circle" size={16} />
      {message}
    </span>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  maxLength?: number;
  error?: string;
  inputRef?: Ref<HTMLInputElement>;
  autoFocus?: boolean;
}

export function TextField({ label, value, onChange, placeholder, autoComplete, maxLength, error, inputRef, autoFocus }: TextFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <input
        id={id}
        ref={inputRef}
        type="text"
        className={styles.input}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        maxLength={maxLength}
        autoFocus={autoFocus}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />
      <FieldError id={errorId} message={error} />
    </div>
  );
}

interface TextAreaProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helper?: string;
  optional?: boolean;
  /** 124px for visitors, 200px for the glasses user. */
  minHeight?: 124 | 200;
  rows?: number;
  maxLength?: number;
}

export function TextArea({ label, value, onChange, placeholder, helper, optional, minHeight = 124, rows = 4, maxLength }: TextAreaProps) {
  const id = useId();
  const helperId = `${id}-helper`;
  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label htmlFor={id} className={styles.label}>
          {label}
        </label>
        {optional && <span className={styles.optional}>Optional</span>}
      </div>
      <textarea
        id={id}
        className={styles.textarea}
        style={{ minHeight }}
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-describedby={helper ? helperId : undefined}
      />
      {helper && (
        <span id={helperId} className={styles.helper}>
          {helper}
        </span>
      )}
    </div>
  );
}

interface ChipGroupProps {
  legend: string;
  name: string;
  options: readonly string[];
  value: string | null;
  onChange: (value: string) => void;
  error?: string;
}

/** A single-select radio group: native radios inside a fieldset, drawn as chips. */
export function ChipGroup({ legend, name, options, value, onChange, error }: ChipGroupProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <fieldset className={styles.fieldset} aria-describedby={error ? errorId : undefined}>
      <legend className={styles.legend}>{legend}</legend>
      <div className={styles.chips}>
        {options.map((option, i) => {
          const optionId = `${id}-${i}`;
          const checked = value === option;
          return (
            <label key={option} htmlFor={optionId} className={checked ? `${styles.chip} ${styles.chipOn}` : styles.chip}>
              <input
                id={optionId}
                type="radio"
                name={name}
                value={option}
                checked={checked}
                onChange={() => onChange(option)}
                className={styles.radio}
              />
              <span>{option}</span>
            </label>
          );
        })}
      </div>
      <FieldError id={errorId} message={error} />
    </fieldset>
  );
}

import { useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "../../components/Button";
import { TextField } from "../../components/Fields";
import { ActionBar, FormMain, PageShell, TitleBlock } from "../../components/PageShell";
import { LIMITS } from "../../config";
import { useGlassesUserFlow } from "./state";

export function NameScreen() {
  const flow = useGlassesUserFlow();
  const navigate = useNavigate();
  const [error, setError] = useState<string>();
  const inputRef = useRef<HTMLInputElement>(null);

  const next = () => {
    if (!flow.name.trim()) {
      setError("Please enter your first name.");
      inputRef.current?.focus();
      return;
    }
    navigate("/setup/context");
  };

  return (
    <PageShell
      title="Your name"
      step={{ current: 1, total: 3 }}
      footer={
        <ActionBar>
          <Button icon="arrow-right" iconAfter onClick={next}>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={640} form>
        <TitleBlock title="What's your name?" lead="Your family and friends will see it when they sign up to help you." />
        <TextField
          label="First name"
          value={flow.name}
          onChange={(name) => {
            flow.setName(name);
            setError(undefined);
          }}
          placeholder="e.g. Rose"
          autoComplete="given-name"
          maxLength={LIMITS.firstName}
          error={error}
          inputRef={inputRef}
        />
      </FormMain>
    </PageShell>
  );
}

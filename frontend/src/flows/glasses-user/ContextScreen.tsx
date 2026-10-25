import { Button } from "../../components/Button";
import { TextArea } from "../../components/Fields";
import { ActionBar, FormMain, PageShell, TitleBlock } from "../../components/PageShell";
import { LIMITS } from "../../config";
import { useGlassesUserFlow } from "./state";

export function ContextScreen() {
  const flow = useGlassesUserFlow();
  return (
    <PageShell
      title="About you"
      step={{ current: 2, total: 3 }}
      footer={
        <ActionBar>
          <Button to="/setup/voice" icon="arrow-right" iconAfter>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={640} form>
        <TitleBlock
          title="Tell us about you"
          lead="This helps Name Tags understand who's who in your life, so the notes about people make sense to you."
        />
        <TextArea
          label="About you"
          value={flow.context}
          onChange={flow.setContext}
          placeholder="Your family, where you live, what you like to be called, what you enjoy"
          helper="Write as much or as little as you like."
          minHeight={200}
          rows={7}
          maxLength={LIMITS.glassesUserContext}
        />
      </FormMain>
    </PageShell>
  );
}

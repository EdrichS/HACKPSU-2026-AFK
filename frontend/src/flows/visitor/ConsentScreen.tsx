import { useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "../../components/Button";
import { ConsentCheckbox, ConsentList } from "../../components/Consent";
import { Icon } from "../../components/Icon";
import { ActionBar, FormMain, PageShell, TitleBlock } from "../../components/PageShell";
import { CONTACT_EMAIL, possessive } from "../../config";
import styles from "./visitor.module.css";
import { useVisitorFlow } from "./state";

export function ConsentScreen() {
  const flow = useVisitorFlow();
  const navigate = useNavigate();
  const [agreed, setAgreed] = useState(flow.consent);
  const rose = flow.glassesUserName;

  const decline = () => {
    flow.reset();
    navigate("/visitor");
  };
  const accept = () => {
    flow.setConsent(true);
    navigate("/visitor/photos");
  };

  return (
    <PageShell
      title="Consent"
      step={{ current: 1, total: 4 }}
      footer={
        <ActionBar>
          <Button variant="secondary" onClick={decline}>
            Decline
          </Button>
          {/* Disabled until the box is ticked: the handoff's suggestion; the state isn't designed. */}
          <Button icon="arrow-right" iconAfter disabled={!agreed} onClick={accept}>
            Continue
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={720}>
        <TitleBlock
          title="Before we start"
          lead={`To help ${rose} recognize you, we need to record some of your biometric data.`}
        />
        {/* The design copy says "she" and "her"; the glasses user's name is used instead, since
            their pronouns aren't collected. */}
        <ConsentList
          items={[
            { icon: "scan-face", title: "Photos of your face", body: `So ${possessive(rose)} glasses can recognize you when you visit.` },
            { icon: "mic", title: "A recording of your voice", body: `So ${possessive(rose)} live captions can show when you're the one talking.` },
            { icon: "id-card", title: "Your name and relationship", body: "Shown next to your face, along with anything you add." },
          ]}
        />
        <p className={styles.privacy}>
          <Icon name="lock" size={18} className={styles.privacyIcon} />
          <span>
            Only used for {possessive(rose)} Name Tags. You can ask us to delete it at any time:{" "}
            {CONTACT_EMAIL ? <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> : "[contact email]"}.
          </span>
        </p>
        <ConsentCheckbox
          checked={agreed}
          onChange={(checked) => {
            setAgreed(checked);
            if (!checked) flow.setConsent(false); // withdrawn: the later steps close again
          }}
        >
          I agree to have my face and voice recorded and stored for Name Tags.
        </ConsentCheckbox>
      </FormMain>
    </PageShell>
  );
}

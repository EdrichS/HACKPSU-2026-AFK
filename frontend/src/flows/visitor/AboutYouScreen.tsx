import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { SubmitError, submissionInProgress, submitVisitor, type SubmitResult } from "../../api/visitor";
import { Button } from "../../components/Button";
import { ChipGroup, TextArea, TextField } from "../../components/Fields";
import { ActionBar, FormMain, Notice, PageShell, TitleBlock } from "../../components/PageShell";
import { LIMITS } from "../../config";
import { RELATIONSHIPS, relationshipFor, useVisitorFlow, type AboutYou } from "./state";

interface Errors {
  name?: string;
  relationship?: string;
  other?: string;
}

function validate(about: AboutYou, rose: string): Errors {
  const errors: Errors = {};
  if (!about.name.trim()) errors.name = "Please enter your first name.";
  if (!about.relationship) errors.relationship = `Please choose how you're related to ${rose}.`;
  else if (about.relationship === "Other" && !about.otherRelationship.trim()) errors.other = "Please say how you're related.";
  return errors;
}

export function AboutYouScreen() {
  const flow = useVisitorFlow();
  const navigate = useNavigate();
  const rose = flow.glassesUserName;
  const about = flow.about;
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<SubmitError | null>(null);
  // An Upload keeps running if the visitor steps away; coming back shows it still going.
  const [busy, setBusy] = useState(() => submissionInProgress() !== null);
  const [focusRequest, setFocusRequest] = useState(0);
  const nameRef = useRef<HTMLInputElement>(null);
  const otherRef = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const watched = useRef<Promise<SubmitResult> | null>(null);

  // After errors render (so aria-invalid and the message are in place), focus the first invalid
  // field; the error itself is announced by its role="alert".
  useEffect(() => {
    if (focusRequest === 0) return;
    if (errors.name) nameRef.current?.focus();
    else if (errors.relationship) document.querySelector<HTMLInputElement>('input[name="relationship"]')?.focus();
    else if (errors.other) otherRef.current?.focus();
    // Only when an Upload asked for it, not on every edit that clears an error.
  }, [focusRequest]);

  const update = (patch: Partial<AboutYou>) => {
    flow.setAbout({ ...about, ...patch });
    // Clear a field's error as soon as it's fixed, not only on the next Upload.
    setErrors((e) => ({
      ...e,
      ...("name" in patch ? { name: undefined } : {}),
      ...("relationship" in patch ? { relationship: undefined, other: undefined } : {}),
      ...("otherRelationship" in patch ? { other: undefined } : {}),
    }));
  };

  const finish = async (submission: Promise<SubmitResult>) => {
    if (watched.current === submission) return; // StrictMode runs the mount effect twice
    watched.current = submission;
    setBusy(true);
    try {
      const result = await submission;
      if (!mounted.current) return;
      if (!result.contextSaved) console.warn("Notes route missing on the backend; the visitor's context text was not saved.");
      const front = flow.photos.find((p) => p.pose === "front") ?? flow.photos[0];
      // Thank you clears the rest once it shows: resetting here would let this step's guard
      // redirect to Intro before the navigation (a transition) commits.
      flow.setSubmitted({ name: result.person.name, photoUrl: front ? URL.createObjectURL(front.blob) : null });
      navigate("/visitor/thanks", { replace: true });
    } catch (e) {
      if (!mounted.current) return;
      const error = e instanceof SubmitError ? e : new SubmitError("other", "Something went wrong. Please try again.");
      if (error.kind === "duplicate") {
        setErrors({
          name: `Someone named ${about.name.trim()} has already signed up as ${rose}'s ${relationshipFor(about)}. Add your last initial to tell you apart.`,
        });
        setFocusRequest((n) => n + 1);
      } else {
        setFailure(error);
      }
      setBusy(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    const running = submissionInProgress();
    if (running) void finish(running);
    return () => {
      mounted.current = false;
    };
  }, []);

  const upload = () => {
    if (busy) return;
    const found = validate(about, rose);
    setErrors(found);
    setFailure(null);
    if (Object.keys(found).length > 0) {
      setFocusRequest((n) => n + 1);
      return;
    }
    void finish(
      submitVisitor({
        name: about.name,
        relationship: relationshipFor(about),
        context: about.context,
        photos: flow.photos,
        voice: flow.voice!.wav,
      }),
    );
  };

  // "Take the photos again" / "Record again": drop what the server rejected, so the step starts
  // empty instead of showing the same photos or recording with Continue enabled.
  const retake = (step: "photos" | "voice") => {
    if (step === "photos") flow.setPhotos([]);
    else flow.setVoice(null);
    navigate(`/visitor/${step}`);
  };

  return (
    <PageShell
      title="About you"
      step={{ current: 4, total: 4 }}
      footer={
        <ActionBar>
          <Button icon="upload" busy={busy} onClick={upload}>
            {busy ? "Uploading…" : "Upload"}
          </Button>
        </ActionBar>
      }
    >
      <FormMain width={640} form>
        <TitleBlock title={`Tell ${rose} about you`} lead={`This is what ${rose} will see next to your face.`} />
        <TextField
          label="First name"
          value={about.name}
          onChange={(name) => update({ name })}
          placeholder="e.g. Maya"
          autoComplete="given-name"
          maxLength={LIMITS.firstName}
          error={errors.name}
          inputRef={nameRef}
        />
        <ChipGroup
          legend={`How are you related to ${rose}?`}
          name="relationship"
          options={RELATIONSHIPS}
          value={about.relationship}
          onChange={(relationship) => update({ relationship })}
          error={errors.relationship}
        />
        {/* Not designed: the handoff suggests a short text field when "Other" is picked. */}
        {about.relationship === "Other" && (
          <TextField
            label={`How do you know ${rose}?`}
            value={about.otherRelationship}
            onChange={(otherRelationship) => update({ otherRelationship })}
            placeholder="e.g. Neighbor"
            maxLength={LIMITS.otherRelationship}
            error={errors.other}
            inputRef={otherRef}
          />
        )}
        <TextArea
          label={`Anything else ${rose} should know?`}
          optional
          value={about.context}
          onChange={(context) => update({ context })}
          placeholder="How you know each other, what you like to talk about, when you usually visit"
          helper={`${rose} will see this as a few short notes beside your name.`}
          minHeight={124}
          rows={4}
          maxLength={LIMITS.visitorContext}
        />
        {failure && <UploadFailure error={failure} onRetake={retake} />}
      </FormMain>
    </PageShell>
  );
}

/** Upload's error and offline states aren't designed; this is a plain notice above the button. */
function UploadFailure({ error, onRetake }: { error: SubmitError; onRetake: (step: "photos" | "voice") => void }) {
  if (error.kind === "no_face") {
    return <Notice action={{ label: "Take the photos again", onClick: () => onRetake("photos") }}>{error.message}</Notice>;
  }
  if (error.kind === "voice") {
    return <Notice action={{ label: "Record again", onClick: () => onRetake("voice") }}>{error.message}</Notice>;
  }
  if (error.kind === "offline") return <Notice>You seem to be offline. Check your connection, then press Upload again.</Notice>;
  return <Notice>We couldn't upload your details. {error.message} Please press Upload to try again.</Notice>;
}

import { useEffect, useMemo, useRef } from "react";
import { useLocation } from "react-router";

import { Captions } from "./Captions";
import { HomeLink, StartButton, WhoButton } from "./Controls";
import { DEMO_CAPTION, DEMO_DIRECTORY, DEMO_FACES, DEMO_PEOPLE } from "./demo";
import { DemoScene } from "./DemoScene";
import { FaceTags } from "./FaceTags";
import { HudStage } from "./HudStage";
import { InfoPanel } from "./InfoPanel";
import { LivePill } from "./LivePill";
import styles from "./LiveView.module.css";
import { choosePanelPerson } from "./people";
import { parseSettings, type HudSettings } from "./settings";
import { useFaceTracks } from "./tracker";
import { useLiveSession } from "./useLiveSession";

/** The glasses live view (HUD) at /live; ?demo=1 shows the mockup's scene instead of the camera. */
export function LiveView() {
  const { search } = useLocation();
  const settings = useMemo(() => parseSettings(search), [search]);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Name Tags · Live view";
    document.body.classList.add(styles.hudBody);
    return () => {
      document.title = previousTitle;
      document.body.classList.remove(styles.hudBody);
    };
  }, []);

  return settings.demo ? <DemoLiveView settings={settings} /> : <CameraLiveView settings={settings} />;
}

/** Space asks "Who is this?", unless a control or text field has focus (it handles Space itself). */
function useSpaceForWho(who: (() => void) | null) {
  useEffect(() => {
    if (!who) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space" && event.key !== " ") return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (target instanceof Element && target.closest("input, textarea, select, button, a[href], [contenteditable]")) return;
      event.preventDefault(); // no page scroll
      if (!event.repeat) who();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [who]);
}

function CameraLiveView({ settings }: { settings: HudSettings }) {
  const video = useRef<HTMLVideoElement>(null);
  const session = useLiveSession(video, settings.mirror);
  const tracks = useFaceTracks(session.faces);
  const person = choosePanelPerson(tracks, session.directory, session.people, session.voicePersonId);
  useSpaceForWho(session.started ? session.who : null);

  return (
    <HudStage
      vars={settings.vars}
      controls={
        <>
          <HomeLink />
          {session.started ? <WhoButton onClick={session.who} disabled={!session.connected} /> : <StartButton onClick={session.start} />}
        </>
      }
    >
      <h1 className="visually-hidden">Name Tags live view</h1>
      <video
        ref={video}
        className={settings.mirror ? `${styles.video} ${styles.mirrored}` : styles.video}
        autoPlay
        muted
        playsInline
        aria-hidden="true"
      />
      <FaceTags tracks={tracks} directory={session.directory} boxes={settings.boxes} />
      {/* Undesigned: before Start there is nothing to report, so the pill waits. */}
      {session.started && (
        <LivePill connected={session.connected} face={session.camera} voice={session.voice} captions={session.captions} />
      )}
      <InfoPanel person={person} />
      <Captions line={session.caption} />
    </HudStage>
  );
}

/** The mockup, rebuilt from the real components. Mirroring is ignored: the illustration isn't a camera. */
function DemoLiveView({ settings }: { settings: HudSettings }) {
  const tracks = useFaceTracks(DEMO_FACES);
  const person = choosePanelPerson(tracks, DEMO_DIRECTORY, DEMO_PEOPLE, null);
  return (
    <HudStage vars={settings.vars} controls={<HomeLink />}>
      <h1 className="visually-hidden">Name Tags live view</h1>
      <DemoScene />
      <FaceTags tracks={tracks} directory={DEMO_DIRECTORY} boxes={settings.boxes} />
      <LivePill connected face voice captions />
      <InfoPanel person={person} />
      <Captions line={DEMO_CAPTION} />
    </HudStage>
  );
}

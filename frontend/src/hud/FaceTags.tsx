import { Fragment, useLayoutEffect, useRef, type ReactNode } from "react";

import type { PresentPerson } from "../api/contract";
import styles from "./FaceTags.module.css";
import { STAGE_HEIGHT, STAGE_WIDTH, bracketBox } from "./geometry";
import { capitalize } from "./people";
import type { TrackView } from "./tracker";

/** The name tag's bottom edge sits this many box heights above the box. */
const NAME_LIFT = 0.3;
const RELATIONSHIP_GAP = 16;
/** Not designed: a face near the frame's edge keeps its tags this far inside it. */
const EDGE = 8;

/**
 * A tag at its designed spot, pushed back inside the frame when the face is near an edge: a
 * face close to the top would otherwise lose its name, the one thing the HUD is there to show.
 * `anchor` is the tag's top edge ("top") or bottom edge ("bottom"), centered on `centerX`.
 */
function StageTag({ className, centerX, y, anchor, children }: { className: string; centerX: number; y: number; anchor: "top" | "bottom"; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    const left = Math.min(Math.max(centerX - width / 2, EDGE), STAGE_WIDTH - EDGE - width);
    const top = Math.min(Math.max(anchor === "bottom" ? y - height : y, EDGE), STAGE_HEIGHT - EDGE - height);
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  });
  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

interface FaceTagsProps {
  tracks: TrackView[];
  directory: ReadonlyMap<number, PresentPerson>;
  /** Corner brackets; ?boxes=0 turns them off. */
  boxes: boolean;
}

/** A bracketed box per face; named faces also get their name and relationship tags. */
export function FaceTags({ tracks, directory, boxes }: FaceTagsProps) {
  return tracks.map((track) => {
    // "unsure" and "unknown" faces get the brackets only.
    const person = track.state === "named" && track.personId !== null ? directory.get(track.personId) : undefined;
    const box = bracketBox(track.box);
    const centerX = box.x + box.width / 2;
    const relationship = person ? capitalize(person.relationship) : "";
    return (
      <Fragment key={track.key}>
        {boxes && (
          <div className={styles.box} style={{ left: box.x, top: box.y, width: box.width, height: box.height }} aria-hidden="true">
            <span className={`${styles.corner} ${styles.topLeft}`} />
            <span className={`${styles.corner} ${styles.topRight}`} />
            <span className={`${styles.corner} ${styles.bottomLeft}`} />
            <span className={`${styles.corner} ${styles.bottomRight}`} />
          </div>
        )}
        {person && (
          <StageTag className={`${styles.tag} ${styles.name}`} centerX={centerX} y={box.y - NAME_LIFT * box.height} anchor="bottom">
            {person.name}
          </StageTag>
        )}
        {relationship && (
          <StageTag className={`${styles.tag} ${styles.relationship}`} centerX={centerX} y={box.y + box.height + RELATIONSHIP_GAP} anchor="top">
            {relationship}
          </StageTag>
        )}
      </Fragment>
    );
  });
}

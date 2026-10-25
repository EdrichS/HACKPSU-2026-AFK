import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";

import { STAGE_HEIGHT, STAGE_WIDTH } from "./geometry";
import styles from "./HudStage.module.css";

interface Fit {
  scale: number;
  left: number;
  top: number;
}

/** Contain the 1600 × 900 frame in a width × height area, centered. */
function fitTo(width: number, height: number): Fit {
  const scale = Math.min(width / STAGE_WIDTH, height / STAGE_HEIGHT);
  return { scale, left: (width - STAGE_WIDTH * scale) / 2, top: (height - STAGE_HEIGHT * scale) / 2 };
}

function useStageFit(viewport: RefObject<HTMLDivElement | null>): Fit {
  const [fit, setFit] = useState(() => fitTo(window.innerWidth, window.innerHeight));
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    // Observing the element, not window "resize", also catches size changes that fire no resize
    // event (device emulation, some kiosk shells).
    const observer = new ResizeObserver(() => {
      const next = fitTo(element.clientWidth, element.clientHeight);
      setFit((previous) =>
        previous.scale === next.scale && previous.left === next.left && previous.top === next.top ? previous : next,
      );
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [viewport]);
  return fit;
}

interface HudStageProps {
  /** The URL settings' CSS variables, set on the stage element. */
  vars?: CSSProperties;
  /**
   * Buttons, laid over the stage at its on-screen size rather than scaled with it, so they stay
   * at least 44px tall on any screen.
   */
  controls?: ReactNode;
  children: ReactNode;
}

/** The HUD's 1600 × 900 reference frame, scaled to fit the window and letterboxed. */
export function HudStage({ vars, controls, children }: HudStageProps) {
  const viewport = useRef<HTMLDivElement>(null);
  const { scale, left, top } = useStageFit(viewport);
  return (
    <div className={styles.viewport} ref={viewport}>
      <div className={styles.stage} style={{ ...vars, transform: `translate(${left}px, ${top}px) scale(${scale})` }}>
        {children}
      </div>
      {controls && (
        <div
          className={styles.controls}
          style={
            { left, top, width: STAGE_WIDTH * scale, height: STAGE_HEIGHT * scale, "--hud-scale": scale } as CSSProperties
          }
        >
          {controls}
        </div>
      )}
    </div>
  );
}

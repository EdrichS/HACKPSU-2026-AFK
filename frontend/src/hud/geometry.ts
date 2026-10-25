import type { Box } from "../api/contract";

/** The HUD's reference frame (Design/screens/glasses/live-view.html). Every HUD position is in these px. */
export const STAGE_WIDTH = 1600;
export const STAGE_HEIGHT = 900;

/** A frame sent to /live: its own size, and the video's size when it was drawn. */
export interface FrameGeometry {
  frameWidth: number;
  frameHeight: number;
  videoWidth: number;
  videoHeight: number;
}

/**
 * A box in the sent frame's pixels to stage px. The video fills the stage with object-fit: cover,
 * so the same scale and centering offsets apply; a mirrored video mirrors its boxes too.
 */
export function frameToStage(box: Box, frame: FrameGeometry, mirror: boolean): Box {
  const cover = Math.max(STAGE_WIDTH / frame.videoWidth, STAGE_HEIGHT / frame.videoHeight);
  const offsetX = (STAGE_WIDTH - frame.videoWidth * cover) / 2;
  const offsetY = (STAGE_HEIGHT - frame.videoHeight * cover) / 2;
  const scaleX = (frame.videoWidth / frame.frameWidth) * cover;
  const scaleY = (frame.videoHeight / frame.frameHeight) * cover;
  const width = box.width * scaleX;
  const x = offsetX + box.x * scaleX;
  return {
    x: mirror ? STAGE_WIDTH - x - width : x,
    y: offsetY + box.y * scaleY,
    width,
    height: box.height * scaleY,
  };
}

/** The bracketed face box: the detected face grown 16px left and right, 18px above, 22px below. */
export function bracketBox(face: Box): Box {
  return { x: face.x - 16, y: face.y - 18, width: face.width + 32, height: face.height + 40 };
}

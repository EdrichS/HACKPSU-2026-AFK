# Name Tags · Design handoff

Reference designs for Name Tags: the glasses live view and two responsive web flows.
Open `screens/index.html` in a browser to click through every screen.

## For the implementer
- `screens/` is the visual source of truth. Exact colors, sizes, spacing and radii are in the inline styles. Match them.
- Rebuild the screens in this project's stack using shared components and the tokens below, rather than copying inline styles.
- The web pages are fully responsive from 360px up. There are no separate mobile pages: the phone frames on the design canvas are the same pages at 390px wide.
- Sample names and illustrations are placeholders (see Content).

## Terms
| Term | Meaning | Sample name |
|---|---|---|
| Glasses user | The person wearing the Meta glasses | Rose |
| Visitor | A family member, friend or caregiver who registers so the glasses can recognize them | Maya |

## Files
| File | Screen |
|---|---|
| `screens/glasses/live-view.html` | Glasses live view (HUD), 1600 × 900 reference frame |
| `screens/visitor/1-intro.html` to `6-thank-you.html` | Visitor sign up flow |
| `screens/glasses-user/1-name.html` to `4-all-set.html` | Glasses user setup flow |

## Design tokens

### Color: web
| Token | Value | Usage |
|---|---|---|
| `ink` | #131418 | Text, primary button, selected chip, filled step segment |
| `ground` | #F3F3F0 | Page background |
| `ground-dots` | rgba(19,20,24,0.09) | 1px dots on a 22px grid over `ground` |
| `surface` | #FFFFFF | Cards, inputs, secondary buttons, thumbnail tiles |
| `muted` | #5B5E66 | Lead text, helper text, step label |
| `border-strong` | #CFD0D4 | Inputs, secondary buttons, unselected chips, checkbox card |
| `border` | #E2E3E6 | Cards and tiles |
| `divider` | #EDEEF0 | Rows inside the consent card |
| `track` | #D3D4D8 | Empty step segments |
| `accent` | #FFD84D | Name highlight, check badges, waveform, done badge |
| `tag-bg` | rgba(19,20,24,0.9) | Pixel logo and name tags on the web |
| `camera-bg` | #1A1B20 | Viewfinder behind the camera feed |
| `camera-scrim` | rgba(12,13,16,0.5) | Area outside the face oval |

### Color: glasses live view
| Token | Value | Usage |
|---|---|---|
| `hud-tag-bg` | rgba(0,0,0,0.45) | Name and relationship tags. Adjustable from 0.2 to 0.85 |
| `hud-accent` | #FFD84D | Relationship text, bullet squares, caption speaker. Alternates tried: #7FDBFF, #9EF0B4, #FFFFFF |
| `hud-glass-bg` | rgba(18,20,26,0.5) | Info panel tint. Adjustable from 0.1 to 0.85; lighter tints lose text contrast over bright scenes |
| `hud-glass-blur` | blur(30px) saturate(175%) | Info panel backdrop filter |
| `hud-glass-edge` | 1px rgba(255,255,255,0.26) border; inset 0 1px 0 rgba(255,255,255,0.55); inset 0 -1px 0 rgba(255,255,255,0.1) | Glass rim and top highlight |
| `hud-glass-sheen` | linear-gradient(155deg, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.05) 34%, transparent 58%) | Overlay inside the panel |
| `hud-caption-bg` | rgba(12,13,17,0.6), blur(18px) saturate(140%), 1px rgba(255,255,255,0.12) border | Caption bar |
| `hud-pill-bg` | rgba(18,20,26,0.55), blur(20px) saturate(160%), 1px rgba(255,255,255,0.18) border | Live status pill |
| `hud-live` | #FF5A4F | Live dot |
| `hud-bracket` | 3px rgba(255,255,255,0.9) | Face box corners |

### Typography
Fonts: **Figtree** 400 to 800 and **Pixelify Sans** 500, both from Google Fonts. Fallbacks: `system-ui` and `'Courier New', monospace`.

| Token | Font | Size / line height / tracking | Weight | Usage |
|---|---|---|---|---|
| `tag-xl` | Pixelify Sans | clamp(46px, 7.2vw, 112px) / 1 / 0.01em | 500 | Intro title tag |
| `tag-sm` | Pixelify Sans | 20px / 1 | 500 | Header logo |
| `display` | Figtree | clamp(32px, 4.2vw, 62px) / 1.08 / -0.025em | 700 | Intro sentence |
| `title-final` | Figtree | clamp(34px, 4.6vw, 66px) / 1.08 / -0.025em | 700 | Thank you, All set |
| `title` | Figtree | clamp(30px, 3.4vw, 48px) / 1.1 / -0.02em | 700 | Step titles |
| `lead` | Figtree | clamp(16px, 1.3vw, 19px) / 1.5 | 400 | Text under titles, in `muted` |
| `prompt` | Figtree | clamp(19px, 1.9vw, 27px) / 1.5 | 500 | Voice paragraph |
| `input` | Figtree | 17px | 400 | Inputs and textareas |
| `button` | Figtree | 17px (18px on Intro) | 600 | Buttons |
| `label` | Figtree | 15px | 600 | Field labels and legends |
| `item-title` | Figtree | 17px | 600 | Consent rows |
| `item-body` | Figtree | 15px / 1.45 | 400 | Consent rows, in `muted` |
| `small` | Figtree | 13px to 14px | 500 to 600 | Helper text, step label, tile labels |

HUD type: name tag Pixelify 40px; relationship tag Pixelify 26px; panel name Figtree 46px / 1.04 / 700; bullets 20px / 1.4 / 500; captions 31px / 1.32 / 600; caption speaker 15px / 700, uppercase, 0.08em; live pill 14px / 600.

### Spacing, sizes, radius, elevation
| Token | Value | Usage |
|---|---|---|
| `gutter` | clamp(20px, 5vw, 64px) | Header and footer side padding |
| `gutter-content` | clamp(20px, 5vw, 32px) | Content column side padding (clamp(20px, 5vw, 48px) on Face photos) |
| `header-pad` | clamp(16px, 2.2vw, 28px) | Header top and bottom |
| `footer-pad` | 12px top, clamp(24px, 4vw, 44px) bottom | Action bar |
| `stack` | clamp(18px, 2.2vw, 28px) | Between blocks on a screen (26px max on form screens) |
| `stack-tight` | 10px | Title to lead |
| `field-gap` | 8px | Label to field, field to helper |
| `control-h` | 56px buttons (58px on Intro), 54px inputs, 44px chips | Control heights |
| `radius-control` | 14px | Buttons, inputs, checkbox card, thumbnail tiles |
| `radius-card` | 18px consent card; 20px prompt card and recorder; 24px viewfinder and photo | Cards |
| `radius-pill` | 999px | Chips and status chips |
| `shadow-card` | 0 1px 2px rgba(19,20,24,0.04), 0 10px 30px rgba(19,20,24,0.05) | Voice prompt card |
| `shadow-photo` | 0 1px 2px rgba(19,20,24,0.08), 0 20px 44px rgba(19,20,24,0.16) | Photo on Thank you |

## Layout and responsive behavior
- **Page shell:** full-height column. Header (logo left, step indicator right), main (fills the space, content centered vertically), footer (actions pinned to the bottom of the screen).
- **Content max widths:** 640px for forms, 720px for Consent, 780px for Voice, 1160px for Face photos.
- **Action bar:** max 560px wide and centered. Two buttons share the row equally; a single button fills it. On phones it spans the full width.
- **Face photos:** two columns on desktop (text 320px to 440px, camera 360px to 600px). Below roughly 790px wide they wrap into one column, text first.
- **Scaling:** type, padding and gaps scale with `clamp()`, so no breakpoints are required. If your stack needs one, use 768px: below it, single column and full-width buttons.

| Width | What changes |
|---|---|
| 1024px and up | Layout as in the desktop frames (1440 × 900 reference) |
| 768px to 1023px | Same layout; sizes interpolate |
| Under 768px | Face photos stacks; every other screen is already one column (390 × 844 reference) |

## Components
| Component | Props / variants | Spec |
|---|---|---|
| LogoTag | size: `sm`, `xl` | `tag-bg` with white Pixelify text. Padding 4px 9px 6px (`sm`) or 0.12em 0.42em 0.2em (`xl`). `xl` adds text-shadow 0.05em 0.05em 0 rgba(0,0,0,0.35). No radius |
| StepIndicator | current, total | "Step 2 of 4" in `small` `muted`, then one segment per step: 22 × 6px, radius 3, gap 4. Done = `ink`, to do = `track`. Segments are decorative |
| Button | `primary`, `secondary`; optional icon | `control-h`, `radius-control`, `button` text, icon gap 10px. Primary: `ink` background, white text. Secondary: `surface` background, 1px `border-strong`. Icons 18px to 20px |
| TextField | label, placeholder | 54px tall, padding 0 16px, 1px `border-strong`, `surface`, `input` text |
| TextArea | label, optional tag, helper | Padding 14px 16px, min height 124px (visitor) or 200px (glasses user), vertical resize. "Optional" tag sits right of the label in `small` `muted` |
| ChipGroup | options, value | Single select radio group inside a fieldset with a legend. Chip: 44px tall, padding 0 18px, `radius-pill`, 16px / 600. Off: `surface`, 1px `border-strong`. On: `ink` background and border, white text. Wraps with 8px gaps |
| ConsentList | items: icon, title, body | `surface` card, 1px `border`, radius 18. Rows padded 16px 20px, `divider` between rows. Icon tile 44px, radius 12, `ground` background, 22px icon |
| ConsentCheckbox | checked | Card with 1px `border-strong`, radius 14, padding 16px 18px. Native 22px checkbox with accent color `ink` |
| CameraViewfinder | status text | `camera-bg`, radius 24, height clamp(300px, 50vh, 520px). Oval guide: 46% of the width, 3:4, centered 46% from the top, 3px white (92%) border, `camera-scrim` outside it. Status chip at the bottom center: white pill, 22px `accent` check badge, 14px / 600 |
| PhotoStrip | 5 shots | 5-column grid, gap 8. Tile: `surface`, 1px `border`, radius 14, padding 7px 4px 6px. 40px round thumbnail; 17px `accent` check badge with a 2px white ring at the bottom right; label 14px / 600. Order: Front, Left, Right, Up, Down |
| VoicePrompt | text | `surface` card, 1px `border`, radius 20, padding clamp(20px, 3vw, 36px), `shadow-card`, `prompt` text |
| Recorder | state, duration | `ink` bar, radius 20, padding 12px 20px 12px 12px. 52px white round play button (aria-label "Play your recording"). Waveform: 40px tall, bars 2px to 4px wide, gap 3, radius 2, `accent`. Right side: duration 16px / 700 with tabular figures, state label 12px / 600 in white at 72% |
| NameTag (web) | name | Pixelify, `tag-bg`, white, padding 5px 12px 7px, clamp(22px, 2vw, 28px). Sits above the visitor photo on Thank you |

## Screens and flows

### Visitor sign up
| # | Screen | Content | Actions |
|---|---|---|---|
| 1 | Intro | LogoTag `xl` "Name Tags". "Help {glassesUserName} remember you." The name gets an `accent` underlay on its lower 42% | Continue → 2 |
| 2 | Consent | "Before we start", lead, ConsentList (face photos, voice recording, name and relationship), privacy line with a lock icon, ConsentCheckbox | Decline → 1, Continue → 3 |
| 3 | Face photos | "Take a few photos", lead, CameraViewfinder with "n of 5 photos taken", PhotoStrip | Retry (retakes all 5), Continue → 4 |
| 4 | Voice | "Read this out loud", lead, VoicePrompt, Recorder | Retry (records again), Continue → 5 |
| 5 | About you | First name (TextField), "How are you related to {glassesUserName}?" (ChipGroup: Son, Daughter, Grandson, Granddaughter, Friend, Caregiver, Other), context (TextArea, optional) | Upload (submits everything) → 6 |
| 6 | Thank you | "Thank you for helping {glassesUserName}.", visitor photo (4:5, radius 24, width clamp(180px, 17vw, 240px), `shadow-photo`) with NameTag above it, "You can now close this website." in `muted` | None |

### Glasses user setup
| # | Screen | Content | Actions |
|---|---|---|---|
| 1 | Name | "What's your name?", lead, First name | Continue → 2 |
| 2 | Context | "Tell us about you", lead, TextArea "About you" with helper | Continue → 3 |
| 3 | Voice | "Read this out loud", lead about telling their voice apart from others, VoicePrompt written in first person, Recorder | Retry, Upload → 4 |
| 4 | All set | `accent` circle (clamp(72px, 6vw, 96px)) with a check, "You're all set, {name}.", one line about name tags appearing as people sign up, "You can now close this website." | None |

### Data collected
| Flow | Data |
|---|---|
| Visitor | Consent flag, 5 face photos (front, left, right, up, down), voice sample of the prompt (about 15 to 20 seconds), first name, relationship, optional context text |
| Glasses user | First name, context text, voice sample of the prompt |

## Glasses live view (HUD)
Reference frame: 1600 × 900, the wearer's view. Scale proportionally to the target display. The room and person are an illustration standing in for the real world or camera feed.

| Element | Position | Spec |
|---|---|---|
| Face box | Around the detected face: about 16px wider on each side, 18px above, 22px below | Four 28px corner brackets, `hud-bracket`, corner radius 12. Can be turned off |
| Name tag | Centered on the face box. Its bottom edge sits 0.30 × box height above the box top | Pixelify 40px, padding 6px 16px 8px, `hud-tag-bg`, white, hard shadow 3px 3px 0 rgba(0,0,0,0.28), no radius |
| Relationship tag | Centered, 16px below the box bottom | Pixelify 26px, padding 5px 12px 7px, `hud-tag-bg`, `hud-accent` text, hard shadow 2px 2px 0 rgba(0,0,0,0.28) |
| Info panel | Fixed: right 44px, top 112px, width 380px | Liquid glass: `hud-glass-bg`, `hud-glass-blur`, `hud-glass-edge`, `hud-glass-sheen`, radius 34, padding 30px 30px 34px, gap 22px, shadow 0 30px 70px rgba(0,0,0,0.32). First name, 1px divider (white 20%), up to 3 bullets (gap 16px) with 8px `hud-accent` squares |
| Captions | Bottom 44px, centered, width 960px (60% of the frame) | `hud-caption-bg`, radius 24, padding 18px 28px 22px, gap 8px. Speaker row: audio-lines icon plus name in `hud-accent`. Text in white; the word still being transcribed is white at 55% with a 3px blinking cursor |
| Live pill | Top 36px, left 40px | `hud-pill-bg`, radius 999, padding 10px 18px 10px 14px. Pulsing 8px `hud-live` dot, "LIVE", a divider, then Face, Voice and Captions with 18px icons |

Behavior:
- Tags follow the face box every frame. Smooth their movement so they don't jitter.
- Panel bullets come from the visitor's context text, summarized to at most 3 short lines (about 40 characters each).
- The caption speaker name comes from voice recognition. The glasses user's own voice sample lets the system tell their speech apart from others.

## States and interactions
Only the states shown in the screens are designed. Items marked **Suggested** are not part of the design; decide them or ask for a design.

| Element | State | Behavior |
|---|---|---|
| Buttons and links | Hover, press, focus | Not designed. **Suggested:** darken 8% on hover, scale 0.98 on press, 3px `accent` focus ring |
| Consent: Continue | Checkbox not checked | Not designed. **Suggested:** disabled until checked |
| Consent: Decline | After declining | Goes back to Intro. No dedicated screen |
| Face photos | Camera permission denied, no face found, capturing (n of 5), low light, failed upload | Not designed |
| Face photos: Continue | Fewer than 5 photos | Not designed. **Suggested:** disabled |
| Recorder | Idle, recording (live waveform, stop), too short, mic denied | Only "Recorded" is designed |
| About you | Missing name or relationship | Not designed. **Suggested:** inline error under the field |
| Relationship "Other" | Selected | Not designed. **Suggested:** reveal a short text field |
| Upload | Uploading, error, offline | Not designed |
| HUD | Unknown face, several faces, low confidence, captions off, unknown speaker | Not designed |

## Motion
| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Live dot | Always | Ring grows from 0 to 9px while fading out | 1.8s, loops | ease-out |
| Caption cursor | While a word is being transcribed | Blink | 1s, loops | steps(1) |

Nothing else is animated in the design. Respect `prefers-reduced-motion` by turning off both loops.

## Content
- **Placeholders:** Rose (glasses user), Maya (visitor), and `[contact email]` on the Consent screen. Every "Rose" in the visitor copy is the glasses user's name from their setup.
- **Consent wording** is a draft. Have it reviewed before collecting real biometric data.
- **Voice prompts:** the visitor paragraph starts "Hi Rose, it's me" and the glasses user paragraph starts "Hello, this is Rose". Keep both phonetically varied and about 15 to 20 seconds long.
- **Character limits** are not designed. **Suggested:** first name 24, context 500 (visitor) and 1000 (glasses user).

## Accessibility
- Every control is a real element: links styled as buttons, buttons, labeled inputs, and radio chips inside a fieldset with a legend.
- Touch targets are at least 44px.
- Body text contrast meets 4.5:1 (`muted` on `ground` is about 5.8:1).
- Focus order follows the page: header, title, fields, actions. Add visible focus styles; the mockups don't show them.
- The step indicator text is read aloud; its segments are aria-hidden. Decorative icons are aria-hidden, and icon-only buttons have aria-labels.
- In any web or phone view of captions, mark the caption region `aria-live="polite"`.

## Assets
- **Fonts:** Figtree and Pixelify Sans from Google Fonts.
- **Icons:** Lucide style, 24px grid, 2px stroke: scan-face, mic, id-card, lock, check, arrow-right, rotate-ccw, upload, play, audio-lines, captions. All are in the Lucide icon library.
- **Illustrations:** the person and room are inline SVG placeholders for the live camera feed and captured photos. Replace them with the real images.

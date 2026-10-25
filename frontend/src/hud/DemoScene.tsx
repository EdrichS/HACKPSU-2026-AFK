import styles from "./LiveView.module.css";

/** The room and visitor illustration from Design/screens/glasses/live-view.html, standing in for the camera. */
export function DemoScene() {
  return (
    <svg className={styles.scene} width="1600" height="900" viewBox="0 0 1600 900" aria-hidden="true">
      <defs>
        <linearGradient id="ntWall" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#DCCFBC" />
          <stop offset="0.55" stopColor="#C2B19B" />
          <stop offset="1" stopColor="#9C8974" />
        </linearGradient>
        <linearGradient id="ntFloor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#73553F" />
          <stop offset="1" stopColor="#3E2C21" />
        </linearGradient>
        <linearGradient id="ntSky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#B7D3E2" />
          <stop offset="1" stopColor="#EAF0EB" />
        </linearGradient>
        <radialGradient id="ntSpill" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFF7E8" stopOpacity="0.7" />
          <stop offset="1" stopColor="#FFF7E8" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ntLamp" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFD98F" stopOpacity="0.75" />
          <stop offset="0.5" stopColor="#FFD98F" stopOpacity="0.22" />
          <stop offset="1" stopColor="#FFD98F" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ntVignette" cx="0.5" cy="0.48" r="0.75">
          <stop offset="0.6" stopColor="#000000" stopOpacity="0" />
          <stop offset="1" stopColor="#000000" stopOpacity="0.45" />
        </radialGradient>
        <radialGradient id="ntFace" cx="0.42" cy="0.38" r="0.75">
          <stop offset="0" stopColor="#D6A07C" />
          <stop offset="1" stopColor="#BC8160" />
        </radialGradient>
        <linearGradient id="ntSweater" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#88A38C" />
          <stop offset="1" stopColor="#67826C" />
        </linearGradient>
        <clipPath id="ntGlass">
          <rect x="114" y="110" width="364" height="404" />
        </clipPath>
      </defs>

      <rect x="0" y="0" width="1600" height="660" fill="url(#ntWall)" />
      <ellipse cx="300" cy="330" rx="440" ry="340" fill="url(#ntSpill)" />

      <rect x="30" y="58" width="520" height="8" rx="4" fill="#5A4C40" />
      <rect x="96" y="92" width="400" height="440" rx="6" fill="#EEE6D8" />
      <rect x="114" y="110" width="364" height="404" fill="url(#ntSky)" />
      <g clipPath="url(#ntGlass)">
        <ellipse cx="180" cy="500" rx="160" ry="110" fill="#9DB898" />
        <ellipse cx="420" cy="520" rx="140" ry="96" fill="#88A684" />
        <ellipse cx="300" cy="570" rx="220" ry="80" fill="#7C9B79" />
      </g>
      <rect x="292" y="110" width="8" height="404" fill="#EEE6D8" />
      <rect x="114" y="306" width="364" height="8" fill="#EEE6D8" />
      <rect x="82" y="526" width="428" height="16" rx="3" fill="#F5EFE5" />
      <path d="M40 66 L112 66 C100 200 122 360 106 566 L40 566 Z" fill="#B5A28A" />
      <path d="M70 80 C64 220 80 380 70 552" fill="none" stroke="#A08D76" strokeWidth="6" strokeLinecap="round" />
      <path d="M480 66 L552 66 L552 566 L486 566 C504 380 482 220 480 66 Z" fill="#B5A28A" />
      <path d="M524 80 C530 220 516 380 526 552" fill="none" stroke="#A08D76" strokeWidth="6" strokeLinecap="round" />

      <rect x="1000" y="150" width="140" height="180" rx="4" fill="#3A322C" />
      <rect x="1012" y="162" width="116" height="156" fill="#E4D9C7" />
      <path d="M1012 286 L1048 246 L1076 272 L1100 252 L1128 280 L1128 318 L1012 318 Z" fill="#9EB29F" />
      <circle cx="1096" cy="204" r="14" fill="#E8B46E" />

      <circle cx="1420" cy="250" r="270" fill="url(#ntLamp)" />
      <path d="M1352 196 L1488 196 L1520 300 L1320 300 Z" fill="#F4E4C4" />
      <rect x="1416" y="300" width="8" height="352" fill="#3A322C" />
      <ellipse cx="1420" cy="654" rx="64" ry="11" fill="#2C2622" />

      <rect x="0" y="646" width="1600" height="16" fill="#E6DCCC" />
      <rect x="0" y="660" width="1600" height="240" fill="url(#ntFloor)" />
      <path d="M0 724 H1600 M0 806 H1600" stroke="#5B4334" strokeWidth="2" opacity="0.5" />
      <ellipse cx="760" cy="852" rx="660" ry="100" fill="#B39E83" opacity="0.5" />

      <rect x="300" y="430" width="900" height="210" rx="42" fill="#5B7176" />
      <rect x="372" y="468" width="150" height="116" rx="26" fill="#D3A86B" transform="rotate(6 447 526)" />
      <rect x="962" y="470" width="140" height="110" rx="26" fill="#C98B7A" transform="rotate(-7 1032 525)" />
      <rect x="272" y="566" width="956" height="104" rx="30" fill="#4C6166" />
      <rect x="246" y="500" width="112" height="176" rx="38" fill="#536A6F" />
      <rect x="1142" y="500" width="112" height="176" rx="38" fill="#536A6F" />

      <ellipse cx="150" cy="690" rx="26" ry="86" fill="#4E7A56" transform="rotate(-24 150 690)" />
      <ellipse cx="196" cy="672" rx="26" ry="96" fill="#5C8A63" transform="rotate(16 196 672)" />
      <ellipse cx="118" cy="730" rx="22" ry="70" fill="#5C8A63" transform="rotate(-52 118 730)" />
      <ellipse cx="234" cy="724" rx="22" ry="72" fill="#4E7A56" transform="rotate(48 234 724)" />
      <ellipse cx="172" cy="648" rx="20" ry="82" fill="#6A9970" transform="rotate(-4 172 648)" />
      <rect x="102" y="758" width="142" height="20" rx="6" fill="#C97A5D" />
      <path d="M112 776 L234 776 L218 900 L128 900 Z" fill="#B96A4F" />

      <path d="M606 336 C598 224 654 168 720 168 C786 168 842 224 834 336 L846 548 C806 574 634 574 594 548 Z" fill="#2B1F1B" />
      <path d="M448 900 L466 700 C476 616 540 570 632 552 L808 552 C900 570 964 616 974 700 L992 900 Z" fill="url(#ntSweater)" />
      <path d="M684 396 L756 396 L762 556 C742 576 698 576 678 556 Z" fill="#B27756" />
      <ellipse cx="720" cy="414" rx="36" ry="16" fill="#985F42" opacity="0.5" />
      <path d="M640 552 C668 600 772 600 800 552 L818 556 C794 622 646 622 622 556 Z" fill="#6A866F" />
      <path d="M598 360 C590 470 598 566 640 650 C622 660 594 660 576 650 C560 560 566 460 580 360 Z" fill="#2B1F1B" />
      <path d="M842 360 C850 470 842 566 800 650 C818 660 846 660 864 650 C880 560 874 460 860 360 Z" fill="#2B1F1B" />
      <ellipse cx="720" cy="318" rx="78" ry="96" fill="url(#ntFace)" />
      <path d="M640 300 C638 226 678 196 726 196 C780 196 808 234 802 296 C778 258 732 242 690 258 C666 268 650 282 640 300 Z" fill="#2B1F1B" />

      <rect x="0" y="0" width="1600" height="900" fill="url(#ntVignette)" />
    </svg>
  );
}

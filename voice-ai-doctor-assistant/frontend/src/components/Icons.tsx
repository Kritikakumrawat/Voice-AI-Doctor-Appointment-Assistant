import type { ReactNode } from "react";

const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
const make = (children: ReactNode) => (props: { size?: number }) => (
  <svg {...base} width={props.size ?? 18} height={props.size ?? 18}>{children}</svg>
);

export const IconOverview = make(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>);
export const IconDoctors = make(<><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.6-3.6 3.4-5.5 7-5.5s6.4 1.9 7 5.5" /><path d="M12 15v3M10.5 16.5h3" /></>);
export const IconCalendar = make(<><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M8 3v4M16 3v4M3.5 10h17" /></>);
export const IconActivity = make(<path d="M3 12h4l2.5-7 5 14L17 12h4" />);
export const IconPhone = make(<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />);
export const IconEnd = make(<path d="M3 14c5-5 13-5 18 0l-2.2 2.2-3-1.6v-2.4a11 11 0 0 0-7.6 0v2.4l-3 1.6L3 14Z" />);
export const IconMic = make(<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></>);
export const IconMicOff = make(<><path d="M3 3l18 18" /><path d="M9 9v2a3 3 0 0 0 5 2.2M15 9.5V6a3 3 0 0 0-5.7-1.3" /><path d="M5.5 11a6.5 6.5 0 0 0 10.4 5.2M18.5 11c0 .8-.1 1.5-.4 2.2M12 17.5V21" /></>);
export const IconSend = make(<path d="M4 12 20 4l-4.5 16-3.5-6.5L4 12Z" />);
export const IconCheck = make(<path d="m5 12.5 4.5 4.5L19 7.5" />);
export const IconX = make(<path d="M6 6l12 12M18 6 6 18" />);
export const IconEye = make(<><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.8" /></>);
export const IconEyeOff = make(<><path d="M3 3l18 18" /><path d="M10.2 5.7A9.5 9.5 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-3 3.8M6.5 7.3A16 16 0 0 0 2.5 12S6 18.5 12 18.5c1.5 0 2.8-.4 4-1" /></>);
export const IconVolume = make(<><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" /></>);
export const IconVolumeOff = make(<><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" /><path d="m16 9.5 5 5M21 9.5l-5 5" /></>);
export const IconSearch = make(<><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>);
export const IconAlert = make(<><path d="M12 4 2.8 19.5h18.4L12 4Z" /><path d="M12 10v4.5M12 17.2v.1" /></>);
export const IconCross = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16M4 12h16" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" /></svg>
);

import { useEffect, useRef } from "react";

interface Props {
  /** Reads the *current* audio levels. Called every animation frame, so nothing is faked. */
  getLevels: () => { mic: number; bot: number };
  active: boolean;
}

const BARS = 36;

/** Bars driven by real mic / assistant audio levels. Flat when there is no audio. */
export function Waveform({ getLevels, active }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const history = useRef<{ mic: number; bot: number }[]>(Array.from({ length: BARS }, () => ({ mic: 0, bot: 0 })));

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);
    let raf = 0;
    let last = 0;
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw);
      if (t - last < 45) return; // ~22 fps is plenty for a meter
      last = t;
      const levels = active ? getLevels() : { mic: 0, bot: 0 };
      history.current.push(levels);
      history.current.shift();
      ctx.clearRect(0, 0, w, h);
      const gap = 3, bw = (w - gap * (BARS - 1)) / BARS;
      history.current.forEach((lv, i) => {
        const v = Math.max(lv.mic, lv.bot);
        const bh = Math.max(3, v * (h - 6));
        ctx.fillStyle = lv.bot >= lv.mic ? "#7fc4ae" : "#e8b04a";
        if (v < 0.02) ctx.fillStyle = "rgba(255,255,255,0.22)";
        const x = i * (bw + gap);
        ctx.beginPath();
        ctx.roundRect(x, (h - bh) / 2, bw, bh, 2);
        ctx.fill();
      });
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [getLevels, active]);

  return <canvas ref={ref} className="wave" aria-hidden="true" />;
}

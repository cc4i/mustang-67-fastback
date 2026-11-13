import type { HudEmojiId } from './types';

export interface EmojiDescriptor {
  id: HudEmojiId;
  shortLabel: string;
  accent: string;
}

export const HUD_EMOJIS: EmojiDescriptor[] = [
  { id: 'HAPPY', shortLabel: 'Happy', accent: '#12E8FF' },
  { id: 'HEART_EYES', shortLabel: 'Follow', accent: '#FF4D8D' },
  { id: 'COOL', shortLabel: 'Cruise', accent: '#38BDF8' },
  { id: 'ALERT_STOP', shortLabel: 'Brake!', accent: '#FF2E2E' },
  { id: 'THINKING', shortLabel: 'Think', accent: '#FBBF24' },
  { id: 'SPEAKING', shortLabel: 'Speak', accent: '#34D399' },
  { id: 'CURIOUS', shortLabel: 'Scan', accent: '#A78BFA' },
  { id: 'EXCITED', shortLabel: 'Boost', accent: '#FB923C' },
  { id: 'PATROL', shortLabel: 'Patrol', accent: '#2DD4BF' },
  { id: 'WINK', shortLabel: 'Wink', accent: '#60A5FA' },
  { id: 'GUARD', shortLabel: 'Guard', accent: '#F87171' },
  { id: 'SLEEPY', shortLabel: 'Idle', accent: '#94A3B8' },
];

/**
 * Renders the 240x240 circular GC9A01 IPS display frame onto a 2D canvas
 * (used both for the 3D rear-window HUD CanvasTexture and the live cockpit preview).
 */
export function drawGc9a01Hud(
  ctx: CanvasRenderingContext2D,
  emoji: HudEmojiId,
  tofMm: number,
  pulsePhase: number
): void {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const cx = w * 0.5;
  const cy = h * 0.5;
  const r = Math.min(w, h) * 0.46;

  const desc = HUD_EMOJIS.find((e) => e.id === emoji) ?? HUD_EMOJIS[0];
  const color = desc.accent;

  ctx.clearRect(0, 0, w, h);

  // Deep radial IPS screen background
  const grad = ctx.createRadialGradient(cx, cy, r * 0.1, cx, cy, r * 1.05);
  grad.addColorStop(0, '#091426');
  grad.addColorStop(0.75, '#040912');
  grad.addColorStop(1, '#020408');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 1.04, 0, Math.PI * 2);
  ctx.fill();

  // Outer glowing telemetry ring
  ctx.strokeStyle = color;
  ctx.lineWidth = w * 0.032;
  ctx.shadowColor = color;
  ctx.shadowBlur = w * 0.06;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.9, 0, Math.PI * 2);
  ctx.stroke();

  ctx.shadowBlur = w * 0.03;
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  const eyeY = cy - r * 0.14;
  const eyeDX = r * 0.32;
  const bounce = Math.sin(pulsePhase * 3.0) * (r * 0.025);

  if (emoji === 'ALERT_STOP') {
    // Urgent crimson octagon / X-eyes + STOP bar
    ctx.lineWidth = w * 0.045;
    for (const sgn of [-1, 1]) {
      const ex = cx + sgn * eyeDX;
      const d = r * 0.13;
      ctx.beginPath();
      ctx.moveTo(ex - d, eyeY - d);
      ctx.lineTo(ex + d, eyeY + d);
      ctx.moveTo(ex + d, eyeY - d);
      ctx.lineTo(ex - d, eyeY + d);
      ctx.stroke();
    }
    ctx.fillRect(cx - r * 0.34, cy + r * 0.2, r * 0.68, r * 0.14);
  } else if (emoji === 'HEART_EYES') {
    for (const sgn of [-1, 1]) {
      const ex = cx + sgn * eyeDX;
      const hr = r * 0.15;
      ctx.beginPath();
      ctx.arc(ex - hr * 0.45, eyeY - hr * 0.2, hr * 0.55, Math.PI, 0);
      ctx.arc(ex + hr * 0.45, eyeY - hr * 0.2, hr * 0.55, Math.PI, 0);
      ctx.lineTo(ex, eyeY + hr * 0.95);
      ctx.closePath();
      ctx.fill();
    }
    ctx.lineWidth = w * 0.04;
    ctx.beginPath();
    ctx.arc(cx, cy + r * 0.1, r * 0.34, 0.15 * Math.PI, 0.85 * Math.PI);
    ctx.stroke();
  } else if (emoji === 'COOL') {
    // Aviator sunglasses bar
    ctx.fillRect(cx - r * 0.56, eyeY - r * 0.12, r * 0.48, r * 0.24);
    ctx.fillRect(cx + r * 0.08, eyeY - r * 0.12, r * 0.48, r * 0.24);
    ctx.lineWidth = w * 0.035;
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.58, eyeY - r * 0.06);
    ctx.lineTo(cx + r * 0.58, eyeY - r * 0.06);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + r * 0.04, cy + r * 0.16, r * 0.28, 0.1 * Math.PI, 0.78 * Math.PI);
    ctx.stroke();
  } else if (emoji === 'SPEAKING') {
    // Equalizer voice waveform bars
    for (const sgn of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(cx + sgn * eyeDX, eyeY, r * 0.12, 0, Math.PI * 2);
      ctx.fill();
    }
    const bars = 5;
    for (let i = 0; i < bars; i++) {
      const bx = cx + (i - 2) * (r * 0.15);
      const bh = r * (0.14 + 0.18 * Math.abs(Math.sin(pulsePhase * 6 + i * 0.9)));
      ctx.fillRect(bx - r * 0.045, cy + r * 0.26 - bh * 0.5, r * 0.09, bh);
    }
  } else if (emoji === 'THINKING') {
    ctx.beginPath();
    ctx.arc(cx - eyeDX, eyeY - r * 0.03, r * 0.11, 0, Math.PI * 2);
    ctx.arc(cx + eyeDX, eyeY + r * 0.03, r * 0.14, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = w * 0.038;
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.24, cy + r * 0.26);
    ctx.lineTo(cx + r * 0.22, cy + r * 0.2);
    ctx.stroke();
  } else if (emoji === 'SLEEPY') {
    ctx.lineWidth = w * 0.038;
    for (const sgn of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(cx + sgn * eyeDX, eyeY, r * 0.14, 0.1 * Math.PI, 0.9 * Math.PI);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(cx, cy + r * 0.26, r * 0.09, 0, Math.PI * 2);
    ctx.stroke();
  } else {
    // Expressive eyes + smile (HAPPY, WINK, CURIOUS, EXCITED, PATROL, GUARD)
    ctx.beginPath();
    ctx.arc(cx - eyeDX, eyeY + bounce, r * 0.13, 0, Math.PI * 2);
    ctx.fill();
    if (emoji === 'WINK') {
      ctx.lineWidth = w * 0.042;
      ctx.beginPath();
      ctx.moveTo(cx + eyeDX - r * 0.14, eyeY);
      ctx.lineTo(cx + eyeDX + r * 0.14, eyeY);
      ctx.stroke();
    } else {
      const rightR = emoji === 'CURIOUS' ? r * 0.17 : r * 0.13;
      ctx.beginPath();
      ctx.arc(cx + eyeDX, eyeY + bounce, rightR, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.lineWidth = w * 0.042;
    ctx.beginPath();
    if (emoji === 'GUARD') {
      ctx.moveTo(cx - r * 0.26, cy + r * 0.25);
      ctx.lineTo(cx + r * 0.26, cy + r * 0.25);
    } else {
      ctx.arc(cx, cy + r * 0.08 + bounce, r * 0.33, 0.16 * Math.PI, 0.84 * Math.PI);
    }
    ctx.stroke();
  }

  // Bottom ToF telemetry readout
  ctx.shadowBlur = 0;
  ctx.font = `600 ${Math.round(w * 0.075)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  ctx.textAlign = 'center';
  ctx.fillStyle = '#E2E8F0';
  ctx.fillText(`${Math.round(tofMm)}mm`, cx, cy + r * 0.68);
}

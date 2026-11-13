export type EditionMode = 'rc' | 'ai';
export type StudioTab = 'assemble' | 'drive' | 'plates';

export interface CameraPreset {
  pos: [number, number, number];
  target: [number, number, number];
}

export interface StageSpec {
  stage: number;
  title: string;
  vector: string;
  xray: boolean;
  camera: CameraPreset;
  summary: string;
  bullets: string[];
}

export interface PlateSpec {
  plate: number;
  group: string;
  title: string;
  colour_name: string;
  colour: string;
  pieces: number;
  pieces_ai?: number;
  notes: string;
  stls: string[];
  stls_ai_extra?: string[];
}

export interface PartMeta {
  node: string;
  label: string;
  category: 'printed' | 'rc_hw' | 'ai_bom' | 'ai_cable' | 'vfx';
  stl: string;
  plate: number | null;
  in_stage1_mule: boolean;
  qty: number;
  colour: string;
  stage_rc: number | null;
  stage_ai: number | null;
  start_offset_3js: [number, number, number];
  tip: string;
}

export interface AssemblyManifest {
  project: string;
  version: string;
  scale: string;
  dimensions_mm: [number, number, number];
  assets: {
    rc_glb: string;
    rc_glb_bytes: number;
    ai_delta_glb: string;
    ai_delta_glb_bytes: number;
  };
  counts: {
    classic_rc: { parts: number; stls: number; pieces: number; plates: number };
    ai_edition: {
      parts: number;
      stls: number;
      pieces: number;
      plates: number;
      bom_modules: number;
      harnesses: number;
    };
    stage1_mule: { stls: number; pieces: number; print_time_hrs: number };
  };
  kinematics: {
    hood_max_deg: number;
    trunk_max_deg: number;
    door_max_deg: number;
    steer_max_deg: number;
    steering_link_shift_mm: number;
    bevel_gear_ratio_pinion_to_axle: [number, number];
    hinge_pivots_3js: Record<string, [number, number, number]>;
  };
  plates: PlateSpec[];
  stages_rc: StageSpec[];
  stages_ai: StageSpec[];
  ai_swapped_shells: string[];
  parts: PartMeta[];
}

export type HudEmojiId =
  | 'HAPPY'
  | 'HEART_EYES'
  | 'COOL'
  | 'ALERT_STOP'
  | 'THINKING'
  | 'SPEAKING'
  | 'CURIOUS'
  | 'EXCITED'
  | 'WINK'
  | 'PATROL'
  | 'GUARD'
  | 'SLEEPY';

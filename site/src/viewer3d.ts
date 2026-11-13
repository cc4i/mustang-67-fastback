import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import type {
  AssemblyManifest,
  CameraPreset,
  EditionMode,
  HudEmojiId,
  PartMeta,
  StudioTab,
} from './types';
import { drawGc9a01Hud } from './hudCanvas';

const XRAY_SHELL_NODES = new Set([
  'Body',
  'Glass_Windshield',
  'Glass_Rear',
  'Hood',
  'TrunkLid',
  'Door_L',
  'Door_R',
  'EngineBlock',
  'ValveCover_L',
  'ValveCover_R',
  'AirCleaner',
  'InteriorTub',
  'BayTub',
  'BootTub',
  'Chassis',
  'DiffCover',
  'WaymoPod',
]);

const PARENT_AXLE_Z = new THREE.Vector3(0, 0, 1);
const PARENT_SHAFT_X = new THREE.Vector3(1, 0, 0);

const ROLLING_CHASSIS_STAGE4_NODES = new Set([
  'Chassis',
  'Knuckle_L',
  'Knuckle_R',
  'SteeringLink',
  'AxleGear',
  'Axle_R',
  'DiffCover',
  'Rim_FL',
  'Rim_FR',
  'Rim_RL',
  'Rim_RR',
  'Tire_FL',
  'Tire_FR',
  'Tire_RL',
  'Tire_RR',
  'RC_KingpinCore_L',
  'RC_KingpinCore_R',
]);

export interface DriveState {
  steerDeg: number; // -15 .. +15
  throttle: number; // -1 .. +1
  hoodDeg: number; // 0 .. 42
  trunkDeg: number; // 0 .. 40
  doorsDeg: number; // 0 .. 55
  showAiBeams: boolean;
  hudEmoji: HudEmojiId;
  tofDistanceMm: number; // 50 .. 400
  emergencyBraking: boolean;
}

interface StoredMatProps {
  opacity: number;
  transparent: boolean;
  depthWrite: boolean;
  emissiveHex: number;
  emissiveIntensity: number;
}

export class MustangStudio3D {
  private container: HTMLElement;
  private manifest: AssemblyManifest;
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private gltfLoader: GLTFLoader;

  private partByNode = new Map<string, PartMeta>();
  private rcNodes = new Map<string, THREE.Object3D>();
  private aiNodes = new Map<string, THREE.Object3D>();
  private restPos = new Map<THREE.Object3D, THREE.Vector3>();
  private restQuat = new Map<THREE.Object3D, THREE.Quaternion>();
  private meshToCanonicalNode = new Map<THREE.Mesh, string>();
  private origMatProps = new Map<THREE.Material, StoredMatProps>();

  private aiLoaded = false;
  private aiLoadingPromise: Promise<void> | null = null;

  private edition: EditionMode = 'rc';
  private tab: StudioTab = 'assemble';
  private currentStage = 1;
  private stageProgress = 1.0; // 0..1 within currentStage
  private xray = false;
  private explodeFactor = 0.0; // 0..1
  private selectedNode: string | null = null;
  private filterPlate: number | null = null;
  private filterMuleOnly = false;

  private hudCanvas: HTMLCanvasElement;
  private hudCtx: CanvasRenderingContext2D;
  private hudTexture: THREE.CanvasTexture;
  private stageDiscMat: THREE.MeshStandardMaterial | null = null;
  private stageDiscMesh: THREE.Mesh | null = null;
  private stageGridMat: THREE.Material | null = null;
  private pulsePhase = 0;
  private wheelSpinAngle = 0;

  private camAnim: {
    fromPos: THREE.Vector3;
    toPos: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
    t: number;
  } | null = null;

  public drive: DriveState = {
    steerDeg: 0,
    throttle: 0,
    hoodDeg: 0,
    trunkDeg: 0,
    doorsDeg: 0,
    showAiBeams: true,
    hudEmoji: 'HAPPY',
    tofDistanceMm: 260,
    emergencyBraking: false,
  };

  private onPartSelect: (node: string | null) => void;
  private onFrameTick?: () => void;
  private raycaster = new THREE.Raycaster();
  private pointerDownPos = new THREE.Vector2();
  private lastTime = performance.now();
  private disposed = false;

  constructor(
    container: HTMLElement,
    manifest: AssemblyManifest,
    onPartSelect: (node: string | null) => void,
    onFrameTick?: () => void
  ) {
    this.container = container;
    this.manifest = manifest;
    this.onPartSelect = onPartSelect;
    this.onFrameTick = onFrameTick;

    for (const p of manifest.parts) {
      this.partByNode.set(p.node, p);
    }

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(container.clientWidth || 960, container.clientHeight || 640);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.12;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0b101b);

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environment = envTex;
    pmrem.dispose();

    this.camera = new THREE.PerspectiveCamera(
      36,
      (container.clientWidth || 960) / (container.clientHeight || 640),
      2,
      2500
    );
    this.camera.position.set(-165, 95, 195);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.07;
    this.controls.minDistance = 45;
    this.controls.maxDistance = 680;
    this.controls.maxPolarAngle = Math.PI * 0.97;
    this.controls.target.set(112, 30, 0);
    this.controls.update();

    this.setupStudioFloorAndLights();

    // Live 240x240 CanvasTexture for the sub-surface GC9A01 Rear Window Emoji HUD
    this.hudCanvas = document.createElement('canvas');
    this.hudCanvas.width = 240;
    this.hudCanvas.height = 240;
    const ctx = this.hudCanvas.getContext('2d');
    if (!ctx) throw new Error('2D canvas context unavailable');
    this.hudCtx = ctx;
    drawGc9a01Hud(this.hudCtx, this.drive.hudEmoji, this.drive.tofDistanceMm, 0);
    this.hudTexture = new THREE.CanvasTexture(this.hudCanvas);
    this.hudTexture.flipY = false;
    this.hudTexture.colorSpace = THREE.SRGBColorSpace;

    const draco = new DRACOLoader();
    draco.setDecoderPath('./draco/');
    this.gltfLoader = new GLTFLoader();
    this.gltfLoader.setDRACOLoader(draco);

    this.bindEvents();
    this.animate();
  }

  private setupStudioFloorAndLights(): void {
    const hemi = new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.7);
    this.scene.add(hemi);

    const keyLight = new THREE.DirectionalLight(0xfff7ed, 1.55);
    keyLight.position.set(-180, 260, 180);
    this.scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x93c5fd, 0.95);
    rimLight.position.set(280, 140, -190);
    this.scene.add(rimLight);

    const underKeyLight = new THREE.DirectionalLight(0xf1f5f9, 1.35);
    underKeyLight.position.set(70, -210, 130);
    this.scene.add(underKeyLight);

    const underFillLight = new THREE.DirectionalLight(0x93c5fd, 0.85);
    underFillLight.position.set(190, -180, -120);
    this.scene.add(underFillLight);

    // Translucent smoked-glass showroom stage (single-sided +Y normal + elevation fade so Underbody views are 100% unobstructed)
    const padGeo = new THREE.CircleGeometry(170, 84);
    padGeo.rotateX(-Math.PI / 2);
    const padMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.24,
      metalness: 0.15,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
      side: THREE.FrontSide,
    });
    const pad = new THREE.Mesh(padGeo, padMat);
    pad.position.set(113, -0.15, 0);
    pad.renderOrder = -2;
    this.stageDiscMat = padMat;
    this.stageDiscMesh = pad;
    this.scene.add(pad);

    const rimGeo = new THREE.RingGeometry(168.8, 170.4, 96);
    rimGeo.rotateX(-Math.PI / 2);
    const rimMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.28,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const rim = new THREE.Mesh(rimGeo, rimMat);
    rim.position.set(113, -0.12, 0);
    rim.renderOrder = -1;
    this.scene.add(rim);

    const grid = new THREE.GridHelper(340, 34, 0x334155, 0x1e293b);
    grid.position.set(113, -0.05, 0);
    grid.renderOrder = -1;
    const gridMat = grid.material as THREE.Material;
    gridMat.transparent = true;
    gridMat.depthWrite = false;
    gridMat.opacity = 0.36;
    this.stageGridMat = gridMat;
    this.scene.add(grid);
  }

  private bindEvents(): void {
    const dom = this.renderer.domElement;
    dom.addEventListener('pointerdown', (e) => {
      this.pointerDownPos.set(e.clientX, e.clientY);
      this.camAnim = null;
    });
    dom.addEventListener('pointerup', (e) => {
      const dist = Math.hypot(e.clientX - this.pointerDownPos.x, e.clientY - this.pointerDownPos.y);
      if (dist > 5) return;
      const rect = dom.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );
      this.pickPart(ndc);
    });
    dom.addEventListener('wheel', () => {
      this.camAnim = null;
    });

    window.addEventListener('resize', () => this.resize());
  }

  public resize(): void {
    if (this.disposed) return;
    const w = Math.max(300, this.container.clientWidth);
    const h = Math.max(260, this.container.clientHeight);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  private cloneMaterialsAndRegister(root: THREE.Object3D, mapTarget: Map<string, THREE.Object3D>): void {
    root.traverse((obj) => {
      if (obj.name) {
        mapTarget.set(obj.name, obj);
        this.restPos.set(obj, obj.position.clone());
        this.restQuat.set(obj, obj.quaternion.clone());
      }
      if (obj instanceof THREE.Mesh) {
        // Resolve canonical part name (handles multi-material sub-meshes parented under a Group AND AI_* shell swaps)
        let ownerName = obj.name;
        let cur: THREE.Object3D | null = obj;
        while (cur) {
          const stripped = cur.name.startsWith('AI_') &&
            this.manifest.ai_swapped_shells.includes(cur.name.slice(3))
            ? cur.name.slice(3)
            : cur.name;
          if (this.partByNode.has(stripped) || cur.name.startsWith('AI_VFX_') || cur.name === 'AI_Track_Obstacle') {
            ownerName = stripped;
            break;
          }
          cur = cur.parent;
        }
        this.meshToCanonicalNode.set(obj, ownerName);

        const cloneOne = (m: THREE.Material): THREE.Material => {
          const cloned = m.clone();
          const std = cloned as THREE.MeshStandardMaterial;
          this.origMatProps.set(cloned, {
            opacity: std.opacity ?? 1.0,
            transparent: Boolean(std.transparent),
            depthWrite: std.depthWrite ?? true,
            emissiveHex: std.emissive ? std.emissive.getHex() : 0x000000,
            emissiveIntensity: std.emissiveIntensity ?? 0.0,
          });
          return cloned;
        };

        if (Array.isArray(obj.material)) {
          obj.material = obj.material.map(cloneOne);
        } else if (obj.material) {
          obj.material = cloneOne(obj.material);
        }
      }
    });
  }

  public async loadInitialRcModel(): Promise<void> {
    const gltf = await this.gltfLoader.loadAsync(this.manifest.assets.rc_glb);
    this.cloneMaterialsAndRegister(gltf.scene, this.rcNodes);
    this.scene.add(gltf.scene);
    this.applySceneState();
  }

  public async ensureAiModelLoaded(): Promise<void> {
    if (this.aiLoaded) return;
    if (this.aiLoadingPromise) return this.aiLoadingPromise;

    this.aiLoadingPromise = (async () => {
      const gltf = await this.gltfLoader.loadAsync(this.manifest.assets.ai_delta_glb);
      this.cloneMaterialsAndRegister(gltf.scene, this.aiNodes);

      // Bind live 240x240 HUD CanvasTexture onto AI_GC9A01_Screen
      const screenObj = this.aiNodes.get('AI_GC9A01_Screen');
      if (screenObj) {
        screenObj.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            const hudMat = new THREE.MeshBasicMaterial({
              map: this.hudTexture,
              side: THREE.DoubleSide,
            });
            this.origMatProps.set(hudMat, {
              opacity: 1,
              transparent: false,
              depthWrite: true,
              emissiveHex: 0xffffff,
              emissiveIntensity: 1,
            });
            child.material = hudMat;
          }
        });
      }

      this.scene.add(gltf.scene);
      this.aiLoaded = true;
      this.applySceneState();
    })();

    return this.aiLoadingPromise;
  }

  public async setEdition(ed: EditionMode): Promise<void> {
    if (ed === 'ai' && !this.aiLoaded) {
      await this.ensureAiModelLoaded();
    }
    this.edition = ed;
    const maxStages = ed === 'ai' ? this.manifest.stages_ai.length : this.manifest.stages_rc.length;
    if (this.currentStage > maxStages) {
      this.currentStage = maxStages;
    }
    this.applySceneState();
  }

  public getEdition(): EditionMode {
    return this.edition;
  }

  public setTab(tab: StudioTab): void {
    this.tab = tab;
    if (tab !== 'plates') {
      this.filterPlate = null;
      this.filterMuleOnly = false;
    }
    if (tab === 'drive') {
      // Ensure full car is assembled in Drive mode
      this.stageProgress = 1.0;
    }
    this.applySceneState();
  }

  public setStage(stage: number, progress = 1.0, animateCam = true): void {
    const stages = this.edition === 'ai' ? this.manifest.stages_ai : this.manifest.stages_rc;
    const clamped = Math.max(1, Math.min(stages.length, stage));
    this.currentStage = clamped;
    this.stageProgress = Math.max(0, Math.min(1, progress));
    const spec = stages[clamped - 1];
    if (spec && animateCam) {
      this.xray = spec.xray;
      this.flyToCamera(spec.camera);
    }
    this.applySceneState();
  }

  public setStageProgress(progress: number): void {
    this.stageProgress = Math.max(0, Math.min(1, progress));
    this.applySceneState();
  }

  public setXray(enabled: boolean): void {
    this.xray = enabled;
    this.applySceneState();
  }

  public getXray(): boolean {
    return this.xray;
  }

  public setExplode(factor: number): void {
    this.explodeFactor = Math.max(0, Math.min(1, factor));
    this.applySceneState();
  }

  public setPlateFilter(plate: number | null, muleOnly = false): void {
    this.filterPlate = plate;
    this.filterMuleOnly = muleOnly;
    this.applySceneState();
  }

  public selectNode(node: string | null): void {
    this.selectedNode = node;
    this.applySceneState();
    this.onPartSelect(node);
  }

  public flyToCamera(preset: CameraPreset): void {
    this.camAnim = {
      fromPos: this.camera.position.clone(),
      toPos: new THREE.Vector3(...preset.pos),
      fromTarget: this.controls.target.clone(),
      toTarget: new THREE.Vector3(...preset.target),
      t: 0,
    };
  }

  public drawHudMirror(targetCanvas: HTMLCanvasElement): void {
    const ctx = targetCanvas.getContext('2d');
    if (!ctx) return;
    drawGc9a01Hud(ctx, this.drive.hudEmoji, this.drive.tofDistanceMm, this.pulsePhase);
  }

  private pickPart(ndc: THREE.Vector2): void {
    this.raycaster.setFromCamera(ndc, this.camera);
    const candidates: THREE.Mesh[] = [];
    this.scene.traverseVisible((obj) => {
      if (obj instanceof THREE.Mesh && this.meshToCanonicalNode.has(obj)) {
        const cName = this.meshToCanonicalNode.get(obj)!;
        if (cName.startsWith('AI_VFX_') || cName === 'AI_Track_Obstacle') return;
        // In X-Ray mode, let clicks pass through ghosted exterior shells to inspect internal gears/motors!
        if (this.xray && XRAY_SHELL_NODES.has(cName)) return;
        candidates.push(obj);
      }
    });
    const hits = this.raycaster.intersectObjects(candidates, false);
    if (hits.length > 0) {
      const hitMesh = hits[0].object as THREE.Mesh;
      const canonical = this.meshToCanonicalNode.get(hitMesh) ?? null;
      this.selectNode(canonical === this.selectedNode ? null : canonical);
    } else {
      this.selectNode(null);
    }
  }

  private resolveObjectForPart(nodeName: string): THREE.Object3D | undefined {
    if (this.edition === 'ai' && this.aiLoaded && this.manifest.ai_swapped_shells.includes(nodeName)) {
      return this.aiNodes.get(`AI_${nodeName}`);
    }
    return this.rcNodes.get(nodeName) ?? this.aiNodes.get(nodeName);
  }

  public applySceneState(): void {
    const swappedSet = new Set(this.manifest.ai_swapped_shells);

    // 1. Hide inactive edition's swapped shells & exclusive objects
    for (const shell of swappedSet) {
      const rcObj = this.rcNodes.get(shell);
      const aiObj = this.aiNodes.get(`AI_${shell}`);
      if (rcObj) rcObj.visible = !(this.edition === 'ai' && this.aiLoaded);
      if (aiObj) aiObj.visible = this.edition === 'ai' && this.aiLoaded;
    }

    // Smooth ease-out curve for stage fly-in
    const ease = 1 - Math.pow(1 - this.stageProgress, 3);

    for (const part of this.manifest.parts) {
      const obj = this.resolveObjectForPart(part.node);
      if (!obj) continue;

      // Also ensure non-swapped AI nodes hide in RC mode and RC-only electronics hide in AI mode
      const activeStage = this.edition === 'ai' ? part.stage_ai : part.stage_rc;
      if (activeStage === null) {
        obj.visible = false;
        continue;
      }

      // Visibility based on active StudioTab
      let visible = true;
      let flyT = 1.0; // 1.0 = fully seated, 0.0 = at start_offset_3js
      if (this.tab === 'assemble') {
        if (activeStage > this.currentStage) {
          visible = false;
        } else if (activeStage === this.currentStage) {
          flyT = ease;
        }
      }

      // HoodProp only shows when Hood is propped open (>= 30 deg) in Drive mode
      if (part.node === 'HoodProp') {
        visible = this.tab === 'drive' && this.drive.hoodDeg >= 30;
      }

      obj.visible = visible;
      if (!visible) continue;

      // Compute world offset = fly-in offset + stage-4/5 chassis marriage offset + explode offset
      const rest = this.restPos.get(obj);
      const rQuat = this.restQuat.get(obj);
      if (rest && rQuat) {
        // Reset base rotation first (kinematic rotations apply right after in updateKinematics)
        obj.quaternion.copy(rQuat);

        const worldOffset = new THREE.Vector3(
          part.start_offset_3js[0] * (1 - flyT),
          part.start_offset_3js[1] * (1 - flyT),
          part.start_offset_3js[2] * (1 - flyT)
        );

        // Stage 4 -> Stage 5 Rolling Chassis Marriage:
        // In Assemble mode at Stage 4, hold the rolling chassis 36 mm below Body so every gear & kingpin is unobstructed;
        // in Stage 5, glide the entire rolling chassis straight up (+Y in Three.js) into Body!
        if (this.tab === 'assemble' && ROLLING_CHASSIS_STAGE4_NODES.has(part.node)) {
          if (this.currentStage === 4) {
            worldOffset.y -= 36;
          } else if (this.currentStage === 5) {
            worldOffset.y -= 36 * (1 - ease);
          }
        }

        // Radial / axial Explode slider
        if (this.explodeFactor > 0.001) {
          worldOffset.x += part.start_offset_3js[0] * 0.85 * this.explodeFactor;
          worldOffset.y += part.start_offset_3js[1] * 0.85 * this.explodeFactor;
          worldOffset.z += part.start_offset_3js[2] * 0.85 * this.explodeFactor;
        }

        // Convert worldOffset into parent's local frame if parented (e.g. DoorCard -> Door, Rim_FL -> Knuckle_L)
        if (obj.parent && obj.parent !== this.scene && obj.parent.type !== 'Scene') {
          const parentWorldQuat = new THREE.Quaternion();
          obj.parent.getWorldQuaternion(parentWorldQuat);
          worldOffset.applyQuaternion(parentWorldQuat.invert());
        }

        obj.position.copy(rest).add(worldOffset);
      }

      // Apply material state (X-Ray, Plate/Mule Ghosting, Active-Stage Highlight, Click-Selection Glow)
      const isSelected = this.selectedNode === part.node;
      const isActiveStagePart =
        this.tab === 'assemble' && activeStage === this.currentStage && this.stageProgress < 0.98;

      let ghosted = false;
      if (this.tab === 'plates') {
        if (this.filterMuleOnly) {
          ghosted = !part.in_stage1_mule;
        } else if (this.filterPlate !== null) {
          ghosted = part.plate !== this.filterPlate;
        }
      }

      const isXrayShell = this.xray && XRAY_SHELL_NODES.has(part.node) && !isSelected;

      obj.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        // Ensure child sub-meshes aren't inadvertently hidden
        const mats = Array.isArray(child.material) ? child.material : [child.material];
        for (const m of mats) {
          const orig = this.origMatProps.get(m);
          if (!orig) continue;
          const std = m as THREE.MeshStandardMaterial;

          if (ghosted) {
            std.transparent = true;
            std.opacity = 0.09;
            std.depthWrite = false;
          } else if (isXrayShell) {
            std.transparent = true;
            std.opacity = 0.16;
            std.depthWrite = false;
          } else {
            std.transparent = orig.transparent;
            std.opacity = orig.opacity;
            std.depthWrite = orig.depthWrite;
          }

          if (std.emissive) {
            if (isSelected) {
              std.emissive.setHex(0x38bdf8);
              std.emissiveIntensity = 0.55;
            } else if (isActiveStagePart) {
              std.emissive.setHex(0xf59e0b);
              std.emissiveIntensity = 0.28;
            } else {
              std.emissive.setHex(orig.emissiveHex);
              std.emissiveIntensity = orig.emissiveIntensity;
            }
          }
        }
      });
    }

    // AI Perception VFX Beams & Road Obstacle visibility
    const showVfx =
      this.edition === 'ai' &&
      this.aiLoaded &&
      this.tab === 'drive' &&
      this.drive.showAiBeams;
    for (const vName of ['AI_VFX_FisheyeFOV', 'AI_VFX_ToFBeam', 'AI_Track_Obstacle']) {
      const vObj = this.aiNodes.get(vName);
      if (vObj) vObj.visible = showVfx;
    }

    this.applyKinematicPoses();
  }

  private applyKinematicPoses(): void {
    const hoodDeg = this.tab === 'drive' ? this.drive.hoodDeg : 0;
    const trunkDeg = this.tab === 'drive' ? this.drive.trunkDeg : 0;
    const doorsDeg = this.tab === 'drive' ? this.drive.doorsDeg : 0;
    const steerDeg = this.tab === 'drive' ? this.drive.steerDeg : 0;

    // 1. Hood (+42 deg around Blender +Y = -42 deg around Three.js +Z)
    const hood = this.rcNodes.get('Hood');
    if (hood && this.restQuat.has(hood)) {
      hood.quaternion.copy(this.restQuat.get(hood)!);
      hood.rotateZ(-THREE.MathUtils.degToRad(hoodDeg));
    }

    // 2. TrunkLid (-40 deg around Blender +Y = +40 deg around Three.js +Z)
    const trunk = this.rcNodes.get('TrunkLid');
    if (trunk && this.restQuat.has(trunk)) {
      trunk.quaternion.copy(this.restQuat.get(trunk)!);
      trunk.rotateZ(THREE.MathUtils.degToRad(trunkDeg));
    }

    // 3. Door_L (side = -1) & Door_R (side = +1) around Three.js +Y
    const doorL = this.rcNodes.get('Door_L');
    if (doorL && this.restQuat.has(doorL)) {
      doorL.quaternion.copy(this.restQuat.get(doorL)!);
      doorL.rotateY(-THREE.MathUtils.degToRad(doorsDeg));
    }
    const doorR = this.rcNodes.get('Door_R');
    if (doorR && this.restQuat.has(doorR)) {
      doorR.quaternion.copy(this.restQuat.get(doorR)!);
      doorR.rotateY(THREE.MathUtils.degToRad(doorsDeg));
    }

    // 4. Front Kingpin Steering (Knuckle_L/R +-15 deg around Three.js +Y + coupled SteeringLink shift)
    const steerRad = THREE.MathUtils.degToRad(steerDeg);
    for (const kName of ['Knuckle_L', 'Knuckle_R']) {
      const kn = this.rcNodes.get(kName);
      if (kn && this.restQuat.has(kn)) {
        kn.quaternion.copy(this.restQuat.get(kn)!);
        kn.rotateY(steerRad);
      }
    }
    const link = this.rcNodes.get('SteeringLink');
    if (link && this.restPos.has(link) && this.tab === 'drive' && this.explodeFactor < 0.01) {
      const rPos = this.restPos.get(link)!;
      link.position.set(rPos.x, rPos.y, rPos.z + 4.3 * Math.sin(steerRad));
    }

    // 5. Coupled 7T:9T Bevel Drivetrain & Wheel Spin
    // Left wheels (`Rim_FL`, `Rim_RL`, `Tire_FL`, `Tire_RL`) carry a 180-deg Y flip in `restQuat`
    // so their spoke dishes face outward (+Z_parent). Left-multiplying in parent space (`wheelSpinQuat * restQuat`)
    // rotates BOTH left and right wheels in the same forward (-X) rolling direction around the +Z axle axis!
    const wheelSpinQuat = new THREE.Quaternion().setFromAxisAngle(PARENT_AXLE_Z, this.wheelSpinAngle);
    const shaftSpinQuat = new THREE.Quaternion().setFromAxisAngle(
      PARENT_SHAFT_X,
      -(9 / 7) * this.wheelSpinAngle
    );
    for (const wName of [
      'Rim_FL',
      'Tire_FL',
      'Rim_FR',
      'Tire_FR',
      'Rim_RL',
      'Tire_RL',
      'Rim_RR',
      'Tire_RR',
      'Axle_R',
      'AxleGear',
    ]) {
      const wObj = this.rcNodes.get(wName);
      const baseQ = wObj ? this.restQuat.get(wObj) : undefined;
      if (wObj && baseQ) {
        wObj.quaternion.multiplyQuaternions(wheelSpinQuat, baseQ);
      }
    }
    for (const sName of ['MotorCoupler', 'Driveshaft', 'PinionGear']) {
      const sObj = this.rcNodes.get(sName);
      const baseQ = sObj ? this.restQuat.get(sObj) : undefined;
      if (sObj && baseQ) {
        sObj.quaternion.multiplyQuaternions(shaftSpinQuat, baseQ);
      }
    }

    // 6. AI Obstacle Cone position & VL53L1X emergency reflex color
    if (this.aiLoaded && this.edition === 'ai') {
      const cone = this.aiNodes.get('AI_Track_Obstacle');
      if (cone) {
        // Front bumper sits around X = 0 mm; place obstacle ahead at -tofDistanceMm * 0.42 (scaled visual arena)
        cone.position.set(-14 - this.drive.tofDistanceMm * 0.35, 13, 0);
      }
      const beam = this.aiNodes.get('AI_VFX_ToFBeam');
      if (beam) {
        beam.traverse((ch) => {
          if (ch instanceof THREE.Mesh) {
            const mat = ch.material as THREE.MeshStandardMaterial;
            const alert = this.drive.tofDistanceMm < 120;
            mat.color.setHex(alert ? 0xff1e1e : 0x1ee868);
            if (mat.emissive) {
              mat.emissive.setHex(alert ? 0xff1e1e : 0x1ee868);
              mat.emissiveIntensity = alert ? 4.2 : 2.2;
            }
          }
        });
      }
    }
  }

  private animate = (): void => {
    if (this.disposed) return;
    requestAnimationFrame(this.animate);

    const now = performance.now();
    const dt = Math.min(0.05, (now - this.lastTime) / 1000);
    this.lastTime = now;
    this.pulsePhase += dt;

    // Smooth camera preset flight
    if (this.camAnim) {
      this.camAnim.t = Math.min(1, this.camAnim.t + dt * 2.1);
      const s = 1 - Math.pow(1 - this.camAnim.t, 3);
      this.camera.position.lerpVectors(this.camAnim.fromPos, this.camAnim.toPos, s);
      this.controls.target.lerpVectors(this.camAnim.fromTarget, this.camAnim.toTarget, s);
      if (this.camAnim.t >= 1) this.camAnim = null;
    }

    // VL53L1X < 120 mm Emergency Auto-Brake Reflex in AI Edition
    if (this.edition === 'ai' && this.tab === 'drive' && this.drive.tofDistanceMm < 120) {
      this.drive.emergencyBraking = true;
      if (this.drive.throttle > 0) {
        this.drive.throttle = 0;
      }
      if (this.drive.hudEmoji !== 'ALERT_STOP') {
        this.drive.hudEmoji = 'ALERT_STOP';
      }
    } else {
      this.drive.emergencyBraking = false;
    }

    if (Math.abs(this.drive.throttle) > 0.01 && this.tab === 'drive') {
      this.wheelSpinAngle += this.drive.throttle * dt * 11.5;
      this.applyKinematicPoses();
    }

    if (this.edition === 'ai' && this.aiLoaded) {
      drawGc9a01Hud(this.hudCtx, this.drive.hudEmoji, this.drive.tofDistanceMm, this.pulsePhase);
      this.hudTexture.needsUpdate = true;
    }

    if (this.onFrameTick) {
      this.onFrameTick();
    }

    this.controls.update();

    // Fade translucent stage disc & grid smoothly as camera approaches or orbits below floor plane (Y <= 0)
    const elevT = THREE.MathUtils.clamp(this.camera.position.y / 14.0, 0, 1);
    if (this.stageDiscMat && this.stageDiscMesh) {
      this.stageDiscMat.opacity = 0.22 * elevT;
      this.stageDiscMesh.visible = elevT > 0.01;
    }
    if (this.stageGridMat) {
      this.stageGridMat.opacity = 0.08 + 0.28 * elevT;
    }

    this.renderer.render(this.scene, this.camera);
  };
}

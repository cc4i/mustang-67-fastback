import './styles.css';
import { el, richCodeText } from './dom';
import { HUD_EMOJIS } from './hudCanvas';
import type {
  AssemblyManifest,
  CameraPreset,
  EditionMode,
  PartMeta,
  StudioTab,
} from './types';
import { MustangStudio3D } from './viewer3d';

const CAMERA_PRESETS: Record<string, { label: string; preset: CameraPreset; xray?: boolean }> = {
  front34: { label: 'Front 3/4', preset: { pos: [-165, 88, 190], target: [112, 30, 0] }, xray: false },
  rear34: { label: 'Rear 3/4', preset: { pos: [355, 92, 165], target: [125, 34, 0] }, xray: false },
  engine: { label: '289 V8 Bay', preset: { pos: [-55, 118, 92], target: [62, 26, 0] }, xray: false },
  gears: { label: '7T:9T Gears', preset: { pos: [215, 22, 78], target: [176, 18, 0] }, xray: true },
  cabin: { label: 'Twin-Cowl Cabin', preset: { pos: [148, 86, 110], target: [98, 36, 0] }, xray: false },
  chassis: { label: 'Underbody', preset: { pos: [113, -195, 165], target: [113, 14, 0] }, xray: false },
};

function parseInitialUrlParams(): {
  edition: EditionMode;
  tab: StudioTab;
  stage: number;
  xray: boolean;
  mule: boolean;
} {
  const params = new URLSearchParams(window.location.search);
  const rawEd = params.get('edition');
  const edition: EditionMode = rawEd === 'ai' ? 'ai' : 'rc';

  const rawMode = params.get('mode');
  const tab: StudioTab =
    rawMode === 'drive' || rawMode === 'plates' || rawMode === 'assemble' ? rawMode : 'assemble';

  const rawStage = Number.parseInt(params.get('stage') ?? '1', 10);
  const stage = Number.isFinite(rawStage) ? Math.max(1, Math.min(8, rawStage)) : 1;

  const xray = params.get('xray') === '1';
  const mule = params.get('mule') === '1';
  return { edition, tab, stage, xray, mule };
}

async function bootstrap(): Promise<void> {
  const appRoot = document.getElementById('app');
  if (!appRoot) return;

  const initParams = parseInitialUrlParams();

  // Loading banner inside viewport
  const loadingText = el('span', null, 'Loading 1:20 Mustang 3D CAD Meshes (Draco GLB)...');
  const loadingBanner = el('div', { className: 'loading-banner' }, el('div', { className: 'spinner' }), loadingText);

  const canvasMount = el('div', { className: 'canvas-mount' });
  const partToast = el('div', { className: 'part-toast hidden', role: 'status' });

  // Top Header
  const btnRc = el('button', { className: 'edition-btn active-rc', type: 'button' }, 'Classic RC (53 STLs)');
  const btnAi = el('button', { className: 'edition-btn', type: 'button' }, 'Gemini AI Edition (55 STLs)');
  const editionSwitch = el('div', { className: 'edition-switch', role: 'group', ariaLabel: 'Model Edition' }, btnRc, btnAi);

  const headerSubtitle = el(
    'span',
    { className: 'brand-subtitle' },
    '1:20 Scale (226 x 91 x 66 mm) · 100% Procedural Blender Python · 0.0 mm³ Verified'
  );

  const topHeader = el(
    'header',
    { className: 'top-header' },
    el(
      'div',
      { className: 'brand-group' },
      el('div', { className: 'brand-emblem' }, '67'),
      el(
        'div',
        { className: 'brand-titles' },
        el('h1', { className: 'brand-title' }, '1967 Ford Mustang Fastback (e-Mustang) — 3D Studio'),
        headerSubtitle
      )
    ),
    el(
      'div',
      { className: 'header-controls' },
      editionSwitch,
      el(
        'a',
        {
          className: 'repo-link',
          href: 'https://github.com/cc4i/mustang-67-fastback',
          target: '_blank',
          rel: 'noopener noreferrer',
        },
        'GitHub Repo & Print Guides ↗'
      )
    )
  );

  // Floating Viewport Toolbar
  const xrayBtn = el('button', { className: 'tool-btn', type: 'button' }, 'X-Ray Shell');
  const explodeInput = el('input', {
    type: 'range',
    min: '0',
    max: '100',
    step: '1',
    value: '0',
    ariaLabel: 'Explode Assembly View',
  }) as HTMLInputElement;

  const camCluster = el('div', { className: 'toolbar-cluster' });
  const rightToolCluster = el(
    'div',
    { className: 'toolbar-cluster' },
    xrayBtn,
    el('label', { className: 'explode-inline' }, 'Explode', explodeInput)
  );

  const viewportHint = el(
    'div',
    { className: 'viewport-hint' },
    'Drag: Orbit · Scroll: Zoom · Right-Drag: Pan · Click Part: Inspect STL'
  );
  const viewportToolbar = el('div', { className: 'viewport-toolbar' }, camCluster, rightToolCluster);
  const viewportZone = el(
    'section',
    { className: 'viewport-zone' },
    canvasMount,
    viewportToolbar,
    partToast,
    viewportHint,
    loadingBanner
  );

  // Right Dock Mode Tabs
  const tabAssemble = el('button', { className: 'mode-tab active', type: 'button' }, '1. Assemble');
  const tabDrive = el('button', { className: 'mode-tab', type: 'button' }, '2. Test-Drive');
  const tabPlates = el('button', { className: 'mode-tab', type: 'button' }, '3. 9 Plates');
  const dockScroll = el('div', { className: 'dock-scroll' });

  const controlDock = el(
    'aside',
    { className: 'control-dock' },
    el('div', { className: 'mode-tabs' }, tabAssemble, tabDrive, tabPlates),
    dockScroll
  );

  const studioBody = el('main', { className: 'studio-body' }, viewportZone, controlDock);
  appRoot.replaceChildren(topHeader, studioBody);

  // Fetch structured manifest
  const res = await fetch('./assets/assembly_manifest.json');
  if (!res.ok) {
    loadingText.textContent = 'Failed to load assembly_manifest.json';
    return;
  }
  const manifest = (await res.json()) as AssemblyManifest;
  const partMap = new Map<string, PartMeta>(manifest.parts.map((p) => [p.node, p]));

  let activeTab: StudioTab = initParams.tab;
  let activeStage = initParams.stage;
  let stageScrub = 1.0;
  let isPlayingBuild = false;
  let activePlateFilter: number | null = null;
  let activeMuleFilter = initParams.mule;
  let hudMirrorCanvas: HTMLCanvasElement | null = null;
  let throttleSliderRef: HTMLInputElement | null = null;
  let throttleValRef: HTMLElement | null = null;
  let steerSliderRef: HTMLInputElement | null = null;
  let steerValRef: HTMLElement | null = null;
  let reflexBannerRef: HTMLElement | null = null;

  const heldKeys = new Set<string>();

  const viewer = new MustangStudio3D(
    canvasMount,
    manifest,
    (selectedNode) => {
      renderPartToast(selectedNode);
      updateSelectedPartChips(selectedNode);
    },
    () => {
      // Frame tick for keyboard driving & build playback
      handleFrameTick();
    }
  );

  // Populate Camera Preset Buttons
  for (const [key, item] of Object.entries(CAMERA_PRESETS)) {
    const b = el(
      'button',
      {
        className: 'tool-btn',
        type: 'button',
        dataset: { cam: key },
        onClick: () => {
          if (item.xray !== undefined) {
            viewer.setXray(item.xray);
            syncXrayBtn();
          }
          if (key === 'engine' && activeTab === 'drive' && viewer.drive.hoodDeg < 35) {
            viewer.drive.hoodDeg = manifest.kinematics.hood_max_deg;
            viewer.applySceneState();
            renderDock();
          }
          viewer.flyToCamera(item.preset);
        },
      },
      item.label
    );
    camCluster.appendChild(b);
  }

  function syncXrayBtn(): void {
    xrayBtn.classList.toggle('active', viewer.getXray());
  }

  xrayBtn.addEventListener('click', () => {
    viewer.setXray(!viewer.getXray());
    syncXrayBtn();
  });

  explodeInput.addEventListener('input', () => {
    const v = Number(explodeInput.value) / 100;
    viewer.setExplode(v);
  });

  function renderPartToast(nodeName: string | null): void {
    if (!nodeName) {
      partToast.classList.add('hidden');
      viewportHint.style.display = '';
      partToast.replaceChildren();
      return;
    }
    const meta = partMap.get(nodeName);
    if (!meta) {
      partToast.classList.add('hidden');
      viewportHint.style.display = '';
      return;
    }
    viewportHint.style.display = 'none';

    const dot = el('span', { className: 'colour-dot' });
    dot.style.backgroundColor = meta.colour;

    const badges = el(
      'div',
      { className: 'toast-badges' },
      meta.stl ? el('span', { className: 'meta-pill' }, meta.stl) : null,
      meta.plate ? el('span', { className: 'meta-pill' }, `Bambu Plate ${meta.plate}`) : null,
      meta.qty > 1 ? el('span', { className: 'meta-pill' }, `Qty ×${meta.qty}`) : null,
      meta.in_stage1_mule ? el('span', { className: 'meta-pill' }, 'Stage-1 Mule Part') : null
    );

    const tipP = el('p', { className: 'toast-tip' });
    tipP.appendChild(richCodeText(meta.tip));

    partToast.replaceChildren(
      el(
        'div',
        { className: 'toast-head' },
        el('div', { className: 'toast-title-wrap' }, dot, el('span', { className: 'toast-title' }, meta.label)),
        el('button', { className: 'close-btn', type: 'button', onClick: () => viewer.selectNode(null) }, 'Close ✕')
      ),
      badges,
      tipP
    );
    partToast.classList.remove('hidden');
  }

  function updateSelectedPartChips(selectedNode: string | null): void {
    const chips = dockScroll.querySelectorAll<HTMLElement>('[data-part-node]');
    chips.forEach((ch) => {
      ch.classList.toggle('selected', ch.dataset.partNode === selectedNode);
    });
  }

  function syncHeaderButtons(): void {
    const ed = viewer.getEdition();
    btnRc.classList.toggle('active-rc', ed === 'rc');
    btnAi.classList.toggle('active-ai', ed === 'ai');
    tabAssemble.classList.toggle('active', activeTab === 'assemble');
    tabDrive.classList.toggle('active', activeTab === 'drive');
    tabPlates.classList.toggle('active', activeTab === 'plates');
    syncXrayBtn();
  }

  function getActiveStages() {
    return viewer.getEdition() === 'ai' ? manifest.stages_ai : manifest.stages_rc;
  }

  function renderAssembleTab(): void {
    const stages = getActiveStages();
    if (activeStage > stages.length) activeStage = stages.length;
    const curSpec = stages[activeStage - 1];

    // Stage Pills
    const stepper = el('div', { className: 'stage-stepper' });
    for (const st of stages) {
      const cls =
        st.stage === activeStage
          ? 'stage-pill current'
          : st.stage < activeStage
            ? 'stage-pill done'
            : 'stage-pill';
      stepper.appendChild(
        el(
          'button',
          {
            className: cls,
            type: 'button',
            onClick: () => {
              isPlayingBuild = false;
              activeStage = st.stage;
              stageScrub = 0.0;
              viewer.setStage(activeStage, 0.0, true);
              syncXrayBtn();
              // Smoothly animate this single stage from 0 -> 1
              animateSingleStageLanding();
              renderDock();
            },
          },
          `S${st.stage}`
        )
      );
    }

    const playBtn = el(
      'button',
      {
        className: 'primary-btn',
        type: 'button',
        onClick: () => {
          if (isPlayingBuild) {
            isPlayingBuild = false;
            renderDock();
            return;
          }
          if (activeStage >= stages.length && stageScrub >= 0.99) {
            activeStage = 1;
          }
          stageScrub = 0.0;
          isPlayingBuild = true;
          viewer.setStage(activeStage, 0.0, true);
          syncXrayBtn();
          renderDock();
        },
      },
      isPlayingBuild ? '⏸ Pause Auto-Build' : '▶ Play Full 3D Build'
    );

    const prevBtn = el(
      'button',
      {
        className: 'secondary-btn',
        type: 'button',
        disabled: activeStage <= 1,
        onClick: () => {
          isPlayingBuild = false;
          activeStage = Math.max(1, activeStage - 1);
          stageScrub = 1.0;
          viewer.setStage(activeStage, 1.0, true);
          syncXrayBtn();
          renderDock();
        },
      },
      '← Prev'
    );

    const nextBtn = el(
      'button',
      {
        className: 'secondary-btn',
        type: 'button',
        onClick: () => {
          isPlayingBuild = false;
          if (activeStage < stages.length) {
            activeStage += 1;
            stageScrub = 0.0;
            viewer.setStage(activeStage, 0.0, true);
            syncXrayBtn();
            animateSingleStageLanding();
            renderDock();
          } else {
            // Final stage reached -> jump straight into Test-Drive Mode!
            activeTab = 'drive';
            viewer.setTab('drive');
            viewer.setXray(false);
            syncHeaderButtons();
            renderDock();
          }
        },
      },
      activeStage < stages.length ? 'Next →' : 'Drive It! →'
    );

    const scrubVal = el('span', { className: 'slider-val' }, `${Math.round(stageScrub * 100)}%`);
    const scrubInput = el('input', {
      type: 'range',
      min: '0',
      max: '100',
      step: '1',
      value: String(Math.round(stageScrub * 100)),
      onInput: (ev) => {
        isPlayingBuild = false;
        stageScrub = Number((ev.target as HTMLInputElement).value) / 100;
        scrubVal.textContent = `${Math.round(stageScrub * 100)}%`;
        viewer.setStageProgress(stageScrub);
      },
    });

    const navCard = el(
      'div',
      { className: 'panel-card' },
      stepper,
      el('div', { className: 'transport-row' }, prevBtn, playBtn, nextBtn),
      el(
        'div',
        { className: 'slider-row' },
        el('div', { className: 'slider-label-line' }, el('span', null, 'Stage Insertion Scrub'), scrubVal),
        scrubInput
      )
    );

    // Current Stage Detail Card
    const summaryP = el('p', { className: 'card-summary' });
    summaryP.appendChild(richCodeText(curSpec.summary));

    const ul = el('ul', { className: 'bullet-list' });
    for (const bText of curSpec.bullets) {
      const li = el('li');
      li.appendChild(richCodeText(bText));
      ul.appendChild(li);
    }

    const stageCard = el(
      'div',
      { className: 'panel-card' },
      el(
        'div',
        { className: 'card-eyebrow' },
        el('span', { className: 'meta-pill' }, `Stage ${curSpec.stage} of ${stages.length}`),
        el('span', { className: 'vector-badge' }, curSpec.vector)
      ),
      el('h2', { className: 'card-title' }, curSpec.title),
      summaryP,
      ul
    );

    // Parts Installed in This Stage
    const ed = viewer.getEdition();
    const stageParts = manifest.parts.filter((p) =>
      curSpec.stage === 5
        ? p.node === 'Chassis' || p.node === 'PinionGear' || p.node === 'AxleGear' || p.node === 'SteeringLink'
        : (ed === 'ai' ? p.stage_ai : p.stage_rc) === curSpec.stage
    );

    const chipsWrap = el('div', { className: 'parts-chip-grid' });
    for (const sp of stageParts) {
      const dot = el('span', { className: 'colour-dot' });
      dot.style.backgroundColor = sp.colour;
      const chip = el(
        'button',
        {
          className: 'part-chip',
          type: 'button',
          dataset: { partNode: sp.node },
          onClick: () => viewer.selectNode(sp.node),
        },
        dot,
        sp.node
      );
      chipsWrap.appendChild(chip);
    }

    const partsCard = el(
      'div',
      { className: 'panel-card' },
      el(
        'div',
        { className: 'slider-label-line' },
        el('span', null, curSpec.stage === 5 ? 'Key Interlocking Nodes' : `Parts in Stage ${curSpec.stage} (${stageParts.length})`),
        el('span', { className: 'slider-val' }, 'Click to Inspect')
      ),
      chipsWrap
    );

    dockScroll.replaceChildren(navCard, stageCard, partsCard);
  }

  let singleLandingRaf = 0;
  function animateSingleStageLanding(): void {
    cancelAnimationFrame(singleLandingRaf);
    const start = performance.now();
    const dur = 680;
    const step = (now: number) => {
      if (isPlayingBuild || activeTab !== 'assemble') return;
      const t = Math.min(1, (now - start) / dur);
      stageScrub = t;
      viewer.setStageProgress(t);
      if (t < 1) {
        singleLandingRaf = requestAnimationFrame(step);
      }
    };
    singleLandingRaf = requestAnimationFrame(step);
  }

  function renderDriveTab(): void {
    const k = manifest.kinematics;

    const steerVal = el('span', { className: 'slider-val' }, `${viewer.drive.steerDeg.toFixed(1)}°`);
    steerValRef = steerVal;
    const steerInput = el('input', {
      type: 'range',
      min: String(-k.steer_max_deg),
      max: String(k.steer_max_deg),
      step: '0.5',
      value: String(viewer.drive.steerDeg),
      onInput: (ev) => {
        viewer.drive.steerDeg = Number((ev.target as HTMLInputElement).value);
        steerVal.textContent = `${viewer.drive.steerDeg.toFixed(1)}°`;
        viewer.applySceneState();
      },
    }) as HTMLInputElement;
    steerSliderRef = steerInput;

    const thrVal = el('span', { className: 'slider-val' }, `${Math.round(viewer.drive.throttle * 100)}%`);
    throttleValRef = thrVal;
    const thrInput = el('input', {
      type: 'range',
      min: '-100',
      max: '100',
      step: '5',
      value: String(Math.round(viewer.drive.throttle * 100)),
      onInput: (ev) => {
        viewer.drive.throttle = Number((ev.target as HTMLInputElement).value) / 100;
        thrVal.textContent = `${Math.round(viewer.drive.throttle * 100)}%`;
      },
    }) as HTMLInputElement;
    throttleSliderRef = thrInput;

    const driveCard = el(
      'div',
      { className: 'panel-card' },
      el('h2', { className: 'card-title' }, 'Live Steering & 7T:9T Bevel Drivetrain'),
      el('p', { className: 'kbd-hint' }, 'Use W/S (or ↑/↓) for Throttle, A/D (or ←/→) to Steer, Space to Stop.'),
      el(
        'div',
        { className: 'slider-row' },
        el('div', { className: 'slider-label-line' }, el('span', null, 'Front Kingpin Steering (±15°)'), steerVal),
        steerInput
      ),
      el(
        'div',
        { className: 'slider-row' },
        el('div', { className: 'slider-label-line' }, el('span', null, 'N25 Motor Throttle (7T → 9T Live Axle)'), thrVal),
        thrInput
      ),
      el(
        'div',
        { className: 'btn-pair' },
        el(
          'button',
          {
            className: 'secondary-btn',
            type: 'button',
            onClick: () => {
              viewer.drive.throttle = 0.55;
              thrInput.value = '55';
              thrVal.textContent = '55%';
              viewer.setXray(true);
              syncXrayBtn();
              viewer.flyToCamera(CAMERA_PRESETS.gears.preset);
            },
          },
          'Inspect Spinning 7T:9T Gears'
        ),
        el(
          'button',
          {
            className: 'secondary-btn',
            type: 'button',
            onClick: () => {
              viewer.drive.throttle = 0;
              viewer.drive.steerDeg = 0;
              thrInput.value = '0';
              steerInput.value = '0';
              thrVal.textContent = '0%';
              steerVal.textContent = '0.0°';
              viewer.applySceneState();
            },
          },
          'Stop / Center'
        )
      )
    );

    // Hinged Body Panels Card
    const hoodVal = el('span', { className: 'slider-val' }, `${Math.round(viewer.drive.hoodDeg)}°`);
    const hoodInput = el('input', {
      type: 'range',
      min: '0',
      max: String(k.hood_max_deg),
      step: '1',
      value: String(viewer.drive.hoodDeg),
      onInput: (ev) => {
        viewer.drive.hoodDeg = Number((ev.target as HTMLInputElement).value);
        hoodVal.textContent = `${Math.round(viewer.drive.hoodDeg)}°`;
        viewer.applySceneState();
      },
    }) as HTMLInputElement;

    const doorsVal = el('span', { className: 'slider-val' }, `${Math.round(viewer.drive.doorsDeg)}°`);
    const doorsInput = el('input', {
      type: 'range',
      min: '0',
      max: String(k.door_max_deg),
      step: '1',
      value: String(viewer.drive.doorsDeg),
      onInput: (ev) => {
        viewer.drive.doorsDeg = Number((ev.target as HTMLInputElement).value);
        doorsVal.textContent = `${Math.round(viewer.drive.doorsDeg)}°`;
        viewer.applySceneState();
      },
    }) as HTMLInputElement;

    const trunkVal = el('span', { className: 'slider-val' }, `${Math.round(viewer.drive.trunkDeg)}°`);
    const trunkInput = el('input', {
      type: 'range',
      min: '0',
      max: String(k.trunk_max_deg),
      step: '1',
      value: String(viewer.drive.trunkDeg),
      onInput: (ev) => {
        viewer.drive.trunkDeg = Number((ev.target as HTMLInputElement).value);
        trunkVal.textContent = `${Math.round(viewer.drive.trunkDeg)}°`;
        viewer.applySceneState();
      },
    }) as HTMLInputElement;

    const panelsCard = el(
      'div',
      { className: 'panel-card' },
      el('h2', { className: 'card-title' }, 'Opening Body Panels & Filament Hinges'),
      el('div', { className: 'slider-row' }, el('div', { className: 'slider-label-line' }, el('span', null, `Hood (+${k.hood_max_deg}° + Prop Rod)`), hoodVal), hoodInput),
      el('div', { className: 'slider-row' }, el('div', { className: 'slider-label-line' }, el('span', null, `Doors (+${k.door_max_deg}° on 1.75 mm Pins)`), doorsVal), doorsInput),
      el('div', { className: 'slider-row' }, el('div', { className: 'slider-label-line' }, el('span', null, `Trunk Lid (-${k.trunk_max_deg}° Rear Deck)`), trunkVal), trunkInput),
      el(
        'div',
        { className: 'btn-pair' },
        el(
          'button',
          {
            className: 'secondary-btn',
            type: 'button',
            onClick: () => {
              viewer.drive.hoodDeg = k.hood_max_deg;
              viewer.drive.doorsDeg = k.door_max_deg;
              viewer.drive.trunkDeg = k.trunk_max_deg;
              hoodInput.value = String(k.hood_max_deg);
              doorsInput.value = String(k.door_max_deg);
              trunkInput.value = String(k.trunk_max_deg);
              hoodVal.textContent = `${k.hood_max_deg}°`;
              doorsVal.textContent = `${k.door_max_deg}°`;
              trunkVal.textContent = `${k.trunk_max_deg}°`;
              viewer.applySceneState();
            },
          },
          'Open All Panels'
        ),
        el(
          'button',
          {
            className: 'secondary-btn',
            type: 'button',
            onClick: () => {
              viewer.drive.hoodDeg = 0;
              viewer.drive.doorsDeg = 0;
              viewer.drive.trunkDeg = 0;
              hoodInput.value = '0';
              doorsInput.value = '0';
              trunkInput.value = '0';
              hoodVal.textContent = '0°';
              doorsVal.textContent = '0°';
              trunkVal.textContent = '0°';
              viewer.applySceneState();
            },
          },
          'Close All'
        )
      )
    );

    const cards: HTMLElement[] = [driveCard, panelsCard];

    // AI Edition Exclusive Cockpit Card (GC9A01 Rear Window HUD + VL53L1X Reflex Simulator)
    if (viewer.getEdition() === 'ai') {
      const mirror = document.createElement('canvas');
      mirror.width = 160;
      mirror.height = 160;
      mirror.className = 'hud-mirror-canvas';
      hudMirrorCanvas = mirror;

      const tofVal = el('span', { className: 'slider-val' }, `${Math.round(viewer.drive.tofDistanceMm)} mm`);
      const tofInput = el('input', {
        type: 'range',
        min: '60',
        max: '380',
        step: '5',
        value: String(viewer.drive.tofDistanceMm),
        onInput: (ev) => {
          viewer.drive.tofDistanceMm = Number((ev.target as HTMLInputElement).value);
          tofVal.textContent = `${Math.round(viewer.drive.tofDistanceMm)} mm`;
          if (viewer.drive.tofDistanceMm >= 120 && viewer.drive.hudEmoji === 'ALERT_STOP') {
            viewer.drive.hudEmoji = 'HAPPY';
          }
          viewer.applySceneState();
          syncEmojiButtons();
        },
      });

      const emojiGrid = el('div', { className: 'emoji-grid' });
      const syncEmojiButtons = () => {
        emojiGrid.querySelectorAll<HTMLButtonElement>('button[data-emoji]').forEach((b) => {
          b.classList.toggle('active', b.dataset.emoji === viewer.drive.hudEmoji);
        });
      };

      for (const em of HUD_EMOJIS) {
        emojiGrid.appendChild(
          el(
            'button',
            {
              className: em.id === viewer.drive.hudEmoji ? 'emoji-btn active' : 'emoji-btn',
              type: 'button',
              dataset: { emoji: em.id },
              onClick: () => {
                viewer.drive.hudEmoji = em.id;
                syncEmojiButtons();
                viewer.flyToCamera({ pos: [265, 92, 130], target: [165, 50, 0] });
              },
            },
            em.shortLabel
          )
        );
      }

      const reflexBanner = el(
        'div',
        { className: 'alert-callout' },
        'VL53L1X < 120 mm Reflex Triggered! (< 20 ms Emergency Auto-Brake + ALERT_STOP HUD)'
      );
      reflexBanner.style.display = viewer.drive.tofDistanceMm < 120 ? 'block' : 'none';
      reflexBannerRef = reflexBanner;

      const beamsToggleBtn = el(
        'button',
        {
          className: viewer.drive.showAiBeams ? 'secondary-btn' : 'secondary-btn',
          type: 'button',
          onClick: () => {
            viewer.drive.showAiBeams = !viewer.drive.showAiBeams;
            beamsToggleBtn.textContent = viewer.drive.showAiBeams
              ? 'Hide FOV & Laser Cones'
              : 'Show FOV & Laser Cones';
            viewer.applySceneState();
          },
        },
        viewer.drive.showAiBeams ? 'Hide FOV & Laser Cones' : 'Show FOV & Laser Cones'
      );

      const aiCockpitCard = el(
        'div',
        { className: 'panel-card' },
        el('h2', { className: 'card-title' }, 'Gemini AI Cockpit: GC9A01 HUD & ToF Reflex'),
        el(
          'div',
          { className: 'hud-cockpit-row' },
          mirror,
          el(
            'div',
            null,
            el('p', { className: 'card-summary' }, 'Live 1.28" Round GC9A01 (240×240 SPI) mounted flush inside the rear fastback glass.'),
            beamsToggleBtn
          )
        ),
        el(
          'div',
          { className: 'slider-row' },
          el('div', { className: 'slider-label-line' }, el('span', null, 'VL53L1X Front Obstacle Distance'), tofVal),
          tofInput
        ),
        reflexBanner,
        emojiGrid
      );

      cards.unshift(aiCockpitCard);
    } else {
      hudMirrorCanvas = null;
      reflexBannerRef = null;
    }

    dockScroll.replaceChildren(...cards);
  }

  function renderPlatesTab(): void {
    const ed = viewer.getEdition();
    const muleCount = manifest.counts.stage1_mule;
    const totalCfg = ed === 'ai' ? manifest.counts.ai_edition : manifest.counts.classic_rc;

    const filterHeaderCard = el(
      'div',
      { className: 'panel-card' },
      el('h2', { className: 'card-title' }, `9-Plate Bambu Lab X2D Breakdown (${totalCfg.stls} STLs → ${totalCfg.pieces} Pcs)`),
      el(
        'p',
        { className: 'card-summary' },
        'Select any plate (or the 2.5-hour Stage-1 Rolling Mule) to ghost everything else and see exactly where those pieces install on the 3D Mustang.'
      ),
      el(
        'div',
        { className: 'btn-pair' },
        el(
          'button',
          {
            className: !activeMuleFilter && activePlateFilter === null ? 'primary-btn' : 'secondary-btn',
            type: 'button',
            onClick: () => {
              activePlateFilter = null;
              activeMuleFilter = false;
              viewer.setPlateFilter(null, false);
              renderPlatesTab();
            },
          },
          `Show All (${totalCfg.pieces} Pcs)`
        ),
        el(
          'button',
          {
            className: activeMuleFilter ? 'primary-btn' : 'secondary-btn',
            type: 'button',
            onClick: () => {
              activePlateFilter = null;
              activeMuleFilter = !activeMuleFilter;
              viewer.setPlateFilter(null, activeMuleFilter);
              renderPlatesTab();
            },
          },
          `Stage-1 Mule (${muleCount.stls} STLs / ~${muleCount.print_time_hrs}h)`
        )
      )
    );

    const list = el('div', { className: 'plate-list' });
    for (const pl of manifest.plates) {
      const pcs = ed === 'ai' && pl.pieces_ai ? pl.pieces_ai : pl.pieces;
      const dot = el('span', { className: 'colour-dot' });
      dot.style.backgroundColor = pl.colour;

      const noteEl = el('div', { className: 'plate-note' });
      noteEl.appendChild(richCodeText(pl.notes));

      const card = el(
        'button',
        {
          className: !activeMuleFilter && activePlateFilter === pl.plate ? 'plate-card active' : 'plate-card',
          type: 'button',
          onClick: () => {
            activeMuleFilter = false;
            activePlateFilter = activePlateFilter === pl.plate ? null : pl.plate;
            viewer.setPlateFilter(activePlateFilter, false);
            renderPlatesTab();
          },
        },
        el(
          'div',
          { className: 'plate-card-top' },
          el('div', { className: 'toast-title-wrap' }, dot, el('span', { className: 'plate-name' }, pl.title)),
          el('span', { className: 'meta-pill' }, `${pcs} pcs`)
        ),
        noteEl
      );
      list.appendChild(card);
    }

    dockScroll.replaceChildren(filterHeaderCard, list);
  }

  function renderDock(): void {
    syncHeaderButtons();
    if (activeTab === 'assemble') {
      renderAssembleTab();
    } else if (activeTab === 'drive') {
      renderDriveTab();
    } else {
      renderPlatesTab();
    }
  }

  function handleFrameTick(): void {
    // 1. Auto-build timeline playback
    if (isPlayingBuild && activeTab === 'assemble') {
      stageScrub += 0.011;
      if (stageScrub >= 1.0) {
        const stages = getActiveStages();
        if (activeStage < stages.length) {
          activeStage += 1;
          stageScrub = 0.0;
          viewer.setStage(activeStage, 0.0, true);
          syncXrayBtn();
          renderDock();
        } else {
          stageScrub = 1.0;
          isPlayingBuild = false;
          viewer.setStageProgress(1.0);
          renderDock();
        }
      } else {
        viewer.setStageProgress(stageScrub);
      }
    }

    // 2. Keyboard WASD / Arrow driving in Test-Drive mode
    if (activeTab === 'drive') {
      let changed = false;
      const maxSteer = manifest.kinematics.steer_max_deg;
      if (heldKeys.has('KeyA') || heldKeys.has('ArrowLeft')) {
        viewer.drive.steerDeg = Math.min(maxSteer, viewer.drive.steerDeg + 0.8);
        changed = true;
      } else if (heldKeys.has('KeyD') || heldKeys.has('ArrowRight')) {
        viewer.drive.steerDeg = Math.max(-maxSteer, viewer.drive.steerDeg - 0.8);
        changed = true;
      }

      if (heldKeys.has('KeyW') || heldKeys.has('ArrowUp')) {
        if (!viewer.drive.emergencyBraking) {
          viewer.drive.throttle = Math.min(1.0, viewer.drive.throttle + 0.04);
          changed = true;
        }
      } else if (heldKeys.has('KeyS') || heldKeys.has('ArrowDown')) {
        viewer.drive.throttle = Math.max(-1.0, viewer.drive.throttle - 0.04);
        changed = true;
      }

      if (changed) {
        viewer.applySceneState();
      }
      if (throttleSliderRef && throttleValRef) {
        throttleSliderRef.value = String(Math.round(viewer.drive.throttle * 100));
        throttleValRef.textContent = `${Math.round(viewer.drive.throttle * 100)}%`;
      }
      if (steerSliderRef && steerValRef) {
        steerSliderRef.value = String(viewer.drive.steerDeg);
        steerValRef.textContent = `${viewer.drive.steerDeg.toFixed(1)}°`;
      }
      if (reflexBannerRef) {
        reflexBannerRef.style.display = viewer.drive.emergencyBraking ? 'block' : 'none';
      }
      if (hudMirrorCanvas && viewer.getEdition() === 'ai') {
        viewer.drawHudMirror(hudMirrorCanvas);
      }
    }
  }

  // Bind Edition & Mode buttons
  btnRc.addEventListener('click', async () => {
    isPlayingBuild = false;
    await viewer.setEdition('rc');
    renderDock();
  });

  btnAi.addEventListener('click', async () => {
    isPlayingBuild = false;
    loadingText.textContent = 'Loading Gemini AI Edition Hardware & Harnesses (0.76 MB)...';
    loadingBanner.classList.remove('hidden');
    await viewer.setEdition('ai');
    loadingBanner.classList.add('hidden');
    renderDock();
  });

  tabAssemble.addEventListener('click', () => {
    activeTab = 'assemble';
    viewer.setTab('assemble');
    viewer.setStage(activeStage, stageScrub, false);
    renderDock();
  });

  tabDrive.addEventListener('click', () => {
    isPlayingBuild = false;
    activeTab = 'drive';
    viewer.setTab('drive');
    renderDock();
  });

  tabPlates.addEventListener('click', () => {
    isPlayingBuild = false;
    activeTab = 'plates';
    viewer.setTab('plates');
    viewer.setPlateFilter(activePlateFilter, activeMuleFilter);
    renderDock();
  });

  window.addEventListener('keydown', (e) => {
    if (e.target instanceof HTMLInputElement) return;
    if (e.code === 'Space' && activeTab === 'drive') {
      e.preventDefault();
      viewer.drive.throttle = 0;
      viewer.applySceneState();
      return;
    }
    heldKeys.add(e.code);
  });

  window.addEventListener('keyup', (e) => {
    heldKeys.delete(e.code);
  });

  // Load initial 3D model & apply URL query deep-link state
  try {
    await viewer.loadInitialRcModel();
    if (initParams.edition === 'ai') {
      loadingText.textContent = 'Loading Gemini AI Edition Hardware & Harnesses (0.76 MB)...';
      await viewer.setEdition('ai');
    }
    viewer.setTab(activeTab);
    if (activeTab === 'assemble') {
      viewer.setStage(activeStage, 1.0, true);
    } else if (activeTab === 'plates' && activeMuleFilter) {
      viewer.setPlateFilter(null, true);
    }
    if (initParams.xray) {
      viewer.setXray(true);
    }
    loadingBanner.classList.add('hidden');
    renderDock();
  } catch {
    loadingText.textContent = 'Error loading 3D GLB assets. Check WebGL support.';
  }
}

void bootstrap();

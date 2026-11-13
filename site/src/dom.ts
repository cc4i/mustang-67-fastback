/**
 * Safe, zero-innerHTML DOM construction utilities (compliant with mandatory-secure-web-skills).
 * All text is inserted strictly via textContent; all elements via createElement.
 */

export type ChildItem = HTMLElement | Text | string | null | undefined | false;

export interface ElementProps {
  className?: string;
  id?: string;
  title?: string;
  type?: string;
  value?: string;
  min?: string;
  max?: string;
  step?: string;
  href?: string;
  target?: string;
  rel?: string;
  role?: string;
  ariaLabel?: string;
  disabled?: boolean;
  dataset?: Record<string, string>;
  onClick?: (ev: MouseEvent) => void;
  onInput?: (ev: Event) => void;
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props?: ElementProps | null,
  ...children: ChildItem[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (props) {
    if (props.className) node.className = props.className;
    if (props.id) node.id = props.id;
    if (props.title) node.title = props.title;
    if (props.role) node.setAttribute('role', props.role);
    if (props.ariaLabel) node.setAttribute('aria-label', props.ariaLabel);
    if (props.disabled !== undefined && 'disabled' in node) {
      (node as HTMLButtonElement).disabled = props.disabled;
    }
    if (props.type && 'type' in node) {
      (node as HTMLInputElement).type = props.type;
    }
    if (props.min !== undefined && 'min' in node) {
      (node as HTMLInputElement).min = props.min;
    }
    if (props.max !== undefined && 'max' in node) {
      (node as HTMLInputElement).max = props.max;
    }
    if (props.step !== undefined && 'step' in node) {
      (node as HTMLInputElement).step = props.step;
    }
    if (props.value !== undefined && 'value' in node) {
      (node as HTMLInputElement).value = props.value;
    }
    if (props.href && node instanceof HTMLAnchorElement) {
      node.href = props.href;
    }
    if (props.target && node instanceof HTMLAnchorElement) {
      node.target = props.target;
    }
    if (props.rel && node instanceof HTMLAnchorElement) {
      node.rel = props.rel;
    }
    if (props.dataset) {
      for (const [k, v] of Object.entries(props.dataset)) {
        node.dataset[k] = v;
      }
    }
    if (props.onClick) {
      (node as HTMLElement).addEventListener('click', props.onClick);
    }
    if (props.onInput) {
      (node as HTMLElement).addEventListener('input', props.onInput);
    }
  }
  for (const ch of children) {
    if (ch === null || ch === undefined || ch === false) continue;
    if (typeof ch === 'string') {
      node.appendChild(document.createTextNode(ch));
    } else {
      node.appendChild(ch);
    }
  }
  return node;
}

/**
 * Safely renders text containing backtick `code` spans without innerHTML.
 */
export function richCodeText(text: string): DocumentFragment {
  const frag = document.createDocumentFragment();
  const segments = text.split('`');
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (!seg) continue;
    if (i % 2 === 1) {
      const codeEl = document.createElement('code');
      codeEl.className = 'inline-code';
      codeEl.textContent = seg;
      frag.appendChild(codeEl);
    } else {
      frag.appendChild(document.createTextNode(seg));
    }
  }
  return frag;
}

/**
 * Vue binding for the ReactDrops soap-bubble material.
 *
 * The renderer, the WebGL pipeline and the shaders in this folder are the
 * unmodified framework-agnostic files from the registry; this file is the port
 * of the React hook that mounts one of them onto a host element.
 *
 * Source: ReactDrops "Bubble UI" (soap-bubble), ReactDrops Component License 1.0
 * — see the licence header in soap-bubble-renderer.ts. Retain it in copies.
 */
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { createSoapBubbleRenderer, normalizeSoapBubble } from './soap-bubble-renderer'

const isDarkScheme = () =>
  typeof window !== 'undefined' &&
  !!window.matchMedia?.('(prefers-color-scheme: dark)').matches

export function useSoapBubble({
  host,
  canvas,
  material = {},
  defaults = {},
  interactive = true,
  backdrop = null
}) {
  const ready = ref(false)
  // shallowRef: the renderer is a plain object of methods, never deep-reactive.
  const engine = shallowRef(null)
  let unbindPointer = null
  let removed = false

  // Light or dark from the nearest data-theme, else the system preference.
  const themeName = () => {
    const theme = host.value?.closest('[data-theme]')?.getAttribute('data-theme')
    if (theme === 'dark') return 'dark'
    if (theme === 'light') return 'light'
    return isDarkScheme() ? 'dark' : 'light'
  }

  const settings = { ...defaults, ...material }
  const tuning = normalizeSoapBubble({
    ...settings,
    environment:
      settings.environment === 'auto'
        ? themeName() === 'dark'
          ? 'studio'
          : 'soft'
        : settings.environment
  })

  const backdropElement = () =>
    backdrop && typeof backdrop === 'object' && 'value' in backdrop ? backdrop.value : backdrop

  // Mirrors the hook's layout effect: CSS carries the fallback (no WebGL) and the
  // palette, so the button still reads correctly before the first frame.
  const applyCss = () => {
    const el = host.value
    if (!el) return
    const open = (value) => (value.trim().toLowerCase() === 'auto' ? 'transparent' : value)
    el.style.setProperty('--soap-bubble-radius', `${tuning.radius / 16}em`)
    el.style.setProperty('--soap-bubble-tint', open(tuning.tint))
    el.style.setProperty('--soap-bubble-soap-color', open(tuning.soapColor))
    el.style.setProperty('--soap-bubble-soap-shade-color', open(tuning.soapShadeColor))
    el.style.setProperty('--soap-bubble-soap-highlight-color', open(tuning.soapHighlightColor))
    el.style.setProperty('--soap-bubble-wobble', String(tuning.wobble))

    const colours = [
      tuning.soapPaletteRed,
      tuning.soapPaletteGold,
      tuning.soapPaletteGreen,
      tuning.soapPaletteCyan,
      tuning.soapPaletteBlue,
      tuning.soapPaletteViolet
    ]
    const stops = [...colours, colours[0]].map(
      (colour) => `color-mix(in srgb, ${colour} ${tuning.oilOpacity * 60}%, transparent)`
    )
    el.style.setProperty(
      '--soap-bubble-custom-palette',
      tuning.soapPalette === 'custom'
        ? `conic-gradient(from 45deg, ${stops.join(', ')})`
        : 'linear-gradient(transparent, transparent)'
    )
  }

  // The film leans toward the pointer and swells on press; keys do the same for
  // keyboards, and a blur releases a press that never got its keyup.
  const bindPointer = (element) => {
    const shape = host.value
    const local = (event) => {
      const rect = shape.getBoundingClientRect()
      const radius = Math.max(1, Math.min(shape.clientWidth, shape.clientHeight) / 2)
      return [
        (event.clientX - rect.left - rect.width / 2) / radius,
        -(event.clientY - rect.top - rect.height / 2) / radius
      ]
    }
    const disabled = () => element.disabled === true
    const onMove = (event) => {
      const [x, y] = local(event)
      engine.value?.pointer(x, y, true)
    }
    const onLeave = (event) => {
      const [x, y] = local(event)
      engine.value?.pointer(x, y, false)
      engine.value?.press(false)
    }
    const onDown = () => {
      if (!disabled()) engine.value?.press(true)
    }
    const onUp = () => engine.value?.press(false)
    // Typing in a field inside the bubble is not a press.
    const typing = (event) =>
      event.target?.matches?.('input, textarea, [contenteditable]') === true
    const onKeyDown = (event) => {
      if (typing(event)) return
      if ((event.key === ' ' || event.key === 'Enter') && !event.repeat && !disabled()) {
        engine.value?.press(true)
      }
    }
    const onKeyUp = (event) => {
      if (typing(event)) return
      if (event.key === ' ' || event.key === 'Enter') engine.value?.press(false)
    }
    const onBlur = () => engine.value?.press(false)

    const listeners = [
      ['pointermove', onMove],
      ['pointerenter', onMove],
      ['pointerleave', onLeave],
      ['pointercancel', onLeave],
      ['pointerdown', onDown],
      ['pointerup', onUp],
      ['keydown', onKeyDown],
      ['keyup', onKeyUp],
      ['blur', onBlur]
    ]
    for (const [type, listener] of listeners) element.addEventListener(type, listener)
    return () => {
      for (const [type, listener] of listeners) element.removeEventListener(type, listener)
    }
  }

  onMounted(() => {
    applyCss()
    if (!canvas.value || !host.value) return

    let renderer = null
    try {
      renderer = createSoapBubbleRenderer(canvas.value, host.value, tuning, () => {
        if (!removed) ready.value = true
      })
    } catch (error) {
      // No WebGL: the CSS fallback stays in charge (data-soap-bubble-ready is
      // never set), which is the component's documented behaviour.
      renderer = null
    }
    engine.value = renderer
    if (!renderer) return

    renderer.setLightTheme(themeName() === 'light')
    renderer.setBackdrop(backdropElement())
    if (interactive) unbindPointer = bindPointer(host.value)
  })

  onBeforeUnmount(() => {
    removed = true
    unbindPointer?.()
    unbindPointer = null
    engine.value?.dispose()
    engine.value = null
  })

  return { ready, tuning, engine, themeName }
}

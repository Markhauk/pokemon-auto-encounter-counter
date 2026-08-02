# Design QA: Generation 3 interface frames 1-20

**Findings**

- No actionable P0, P1, or P2 differences remain. Every frame uses source
  corner pixels and a repeating source edge tile, preserving the distinctive
  patterns at desktop panel sizes.

**Open Questions**

- None for Frame Types 1-20. The source screenshots use a light-gray content
  surface; the implementation intentionally retains the application's existing
  dark content surface because this feature changes frames, not the app theme.

**Implementation Checklist**

- [x] Provide exact pixel-art nine-slice assets for Frame Types 1-20.
- [x] Show all twenty choices in a five-column, scrollable Settings grid.
- [x] Scroll the selector to the active frame when Settings opens.
- [x] Apply the selected frame immediately and persist it across launches.
- [x] Keep Games, Configured Filters, Filter Details, and Preview consistent.
- [x] Frame Scanner Controls, Counters, Live Details, and Live Runtime Log.
- [x] Frame Display Setup, Last Preview, Template Preview, and Logs and State.
- [x] Keep button styling outside the interface-frame rules.
- [x] Include and validate every frame asset in packaged builds.

**Follow-up Polish**

- P3: QGroupBox titles interrupt a short part of the top edge so section names
  remain readable. This is an intentional desktop adaptation of the game frame.

## Evidence

### Source visual truth

- `.tmp/design-qa/reference-frame-1-rse.png` through
  `.tmp/design-qa/reference-frame-20-rse.png`.

Each source is 240 x 160 pixels and represents the corresponding Pokemon Ruby,
Sapphire, and Emerald frame-option screen.

### Implementation captures

- Full Filters views: `.tmp/design-qa/filters-frame-type-1.png` through
  `.tmp/design-qa/filters-frame-type-20.png`.
- Focused Games panels: `.tmp/design-qa/frame-type-1-focused.png` through
  `.tmp/design-qa/frame-type-20-focused.png`.
- Complete selector: `.tmp/design-qa/settings-frame-selector.png`.
- Extended-tab captures: `.tmp/design-qa/dashboard-frame-type-20.png`,
  `.tmp/design-qa/capture-settings-frame-type-20.png`,
  `.tmp/design-qa/templates-frame-type-20.png`, and
  `.tmp/design-qa/logs-state-frame-type-20.png`.
- Unframed control: `.tmp/design-qa/filters-unframed-baseline.png`.

The full captures are 1280 x 921 pixels at device-pixel ratio 1. The intended
window request was 1280 x 860; Qt honored the application's content minimum.
Focused captures are 417 x 131 pixels. No density normalization was applied:
the pixel edges are intentionally rendered at their native one-pixel detail.

### State and interaction

- Native PySide6 application using the Qt Fusion dark palette.
- Filters tab open, `Wild` selected, and one capture produced for every frame.
- Settings tab captured with Frame Type 20 selected and the selector scrolled
  to show the active row.
- Radio selection, automatic active-item scrolling, immediate restyling,
  configuration persistence, and invalid-value fallback are exercised.
- Browser console checks are not applicable to this native desktop interface;
  offscreen rendering completed without application errors.

## Comparison results

### Full view

The four Filters sections use the selected frame consistently. Frames do not
overlap content or buttons. The framed and unframed captures have identical
window dimensions. Twenty selector options remain practical through a
five-column grid and vertical scrolling.

The additional Dashboard, Capture Settings, Templates, and Logs/State captures
confirm that the same frame scales cleanly across wide controls, equal-width
summary panels, tall log panels, preview panels, and compact state summaries.

### Focused regions

Every source image was placed in the same comparison input as its corresponding
focused implementation capture. The checks confirmed:

- Types 1-5 preserve the lavender layers, monochrome lines, red-blue checks,
  mechanical joints, and high-contrast colored bands.
- Types 6-10 preserve mosaic, maze, star-corner, icy zigzag, and golden woven
  patterns.
- Types 11-15 preserve pink scallops, black-gold ornament, blue corner pins,
  sand texture, and white-lavender lace.
- Types 16-20 preserve geometric bands, monochrome braids, yellow-blue dots,
  green leaf weave, and red-blue stitching with jeweled corners.
- Repeating edges join cleanly on wider desktop panels without smoothing,
  stretching, transparency halos, or visible seams.

### Required fidelity surfaces

- Fonts and typography: Segoe UI remains readable and consistent with the
  existing app. Titles, descriptions, and preview copy do not truncate.
- Spacing and layout rhythm: eight-pixel frame bands preserve detail without
  crowding controls. Five columns reduce scrolling while maintaining readable
  cards; the active row is brought into view automatically.
- Colors and visual tokens: frame pixels retain their source palettes. The dark
  app surface and existing selection color are unchanged.
- Image quality and asset fidelity: transparent 40 x 40 raster nine-slices use
  real source-derived corners and edge tiles. No CSS-drawn substitutes,
  scaling blur, or screenshot interiors are present.
- Copy and content: every option has a concise description and the active state
  is explicit.
- Accessibility and interaction: options are native labeled radio buttons,
  keyboard reachable, mutually exclusive, and visibly selected.

## Comparison history

1. The original Types 1-2 used generic Qt `ridge` and `double` borders, a P2
   fidelity mismatch. They were replaced with the same source-derived nine-slice
   system now used by all twenty frames.
2. The ten-option Settings layout was extended to twenty choices. An initial
   Type 20 capture showed the selected radio but left its preview below the
   viewport. The selector now calls `ensureWidgetVisible` for the active option;
   the post-fix capture shows Frame Types 16-20 and the selected Type 20 preview.
3. Source and focused implementation captures for Types 11-20 were compared
   pair by pair. No additional P0, P1, or P2 differences were found.
4. The selected frame was extended to eight requested sections outside the
   Filters tab. Full-tab captures with Frame Type 20 show no clipping, overlap,
   content crowding, or unintended button styling.

## Final result

passed
